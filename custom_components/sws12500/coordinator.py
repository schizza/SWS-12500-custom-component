"""Push coordinator for the SWS-12500 weather station integration.

This module is the runtime heart of the integration:
- `WeatherDataUpdateCoordinator` is a fan-out hub for push payloads.
  Webhook handlers call `async_set_updated_data(...)` and every CoordinatorEntity
  subscribed to the coordinator updates its state.
- `received_data` handles the legacy PWS / WSLink endpoints.
- `received_ecowitt_data` handles the Ecowitt endpoint via the aioecowitt parser.
- `IncorrectDataError` is raised when the integration's auth options are missing.

Kept separate from `__init__.py` so the platforms (sensor / binary_sensor) can
import `WeatherDataUpdateCoordinator` without re-entering the package's
initialization machinery — no more local-import `# noqa: PLC0415` shims.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

import aiohttp.web
from aiohttp.web_exceptions import HTTPUnauthorized
from py_typecheck import checked, checked_or

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import InvalidStateError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .binary_sensor import add_new_binary_sensors
from .const import (
    API_ID,
    API_KEY,
    DEV_DBG,
    DOMAIN,
    ECOWITT_ENABLED,
    ECOWITT_WEBHOOK_ID,
    POCASI_CZ_ENABLED,
    SENSORS_TO_LOAD,
    WINDY_ENABLED,
    WSLINK,
)
from .data import SWSConfigEntry
from .ecowitt import EcowittBridge
from .health_coordinator import HealthCoordinator
from .pocasti_cz import PocasiPush
from .sensor import add_new_sensors
from .utils import (
    anonymize,
    check_disabled,
    loaded_sensors,
    remap_items,
    remap_wslink_items,
    translated_notification,
    translations,
    update_options,
)
from .windy_func import WindyPush

_LOGGER = logging.getLogger(__name__)


class IncorrectDataError(InvalidStateError):
    """Raised when the integration's auth options are missing or invalid."""


class WeatherDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator for push updates.

    Even though Home Assistant's `DataUpdateCoordinator` is often used for polling,
    it also works well as a fan-out mechanism for push integrations:
    - webhook handler updates `self.data` via `async_set_updated_data`
    - all `CoordinatorEntity` instances subscribed update themselves
    """

    def __init__(self, hass: HomeAssistant, config: SWSConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass: HomeAssistant = hass
        self.config: SWSConfigEntry = config
        self.windy: WindyPush = WindyPush(hass, config)
        self.pocasi: PocasiPush = PocasiPush(hass, config)
        self.ecowitt_bridge: EcowittBridge = EcowittBridge(hass, config)

        super().__init__(hass, _LOGGER, name=DOMAIN)

    def _health_coordinator(self) -> HealthCoordinator | None:
        """Return the health coordinator for this config entry."""
        try:
            return self.config.runtime_data.health_coordinator
        except AttributeError:
            return None

    async def received_ecowitt_data(self, webdata: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle incoming Ecowitt webhook payload.

        Uses aioecowitt for payload parsing. Sensors with internal mapping
        join the SWS pipeline; sensors without mapping create native Ecowitt
        entities through the bridge callback.
        """

        health = self._health_coordinator()

        if not checked_or(self.config.options.get(ECOWITT_ENABLED), bool, False):
            if health:
                health.update_ingress_result(
                    webdata,
                    accepted=False,
                    authorized=None,
                    reason="ecowitt_disabled",
                )
            return aiohttp.web.Response(text="Ecowitt disabled", status=403)

        expected_webhook = self.config.options.get(ECOWITT_WEBHOOK_ID, "")
        actual_webhook = webdata.match_info.get("webhook_id", "")

        if not expected_webhook or actual_webhook != expected_webhook:
            _LOGGER.error("Ecowitt: invalid webhook ID")
            if health:
                health.update_ingress_result(
                    webdata,
                    accepted=False,
                    authorized=False,
                    reason="ecowitt_invalid_webhook_id",
                )
            raise HTTPUnauthorized

        post_data = await webdata.post()
        data: dict[str, Any] = dict(post_data)

        mapped_data = await self.ecowitt_bridge.process_payload(data)

        if mapped_data:
            if sensors := check_disabled(mapped_data, self.config):
                newly_discovered = list(sensors)
                if _loaded_sensors := loaded_sensors(self.config):
                    sensors.extend(_loaded_sensors)
                await update_options(self.hass, self.config, SENSORS_TO_LOAD, sensors)

                add_new_binary_sensors(self.hass, self.config, newly_discovered)
                add_new_sensors(self.hass, self.config, newly_discovered)
            self.async_set_updated_data(mapped_data)

        if health:
            health.update_ingress_result(
                webdata,
                accepted=True,
                authorized=True,
                reason="accepted",
            )

        _windy_enabled = checked_or(self.config.options.get(WINDY_ENABLED), bool, False)
        _pocasi_enabled = checked_or(self.config.options.get(POCASI_CZ_ENABLED), bool, False)
        if _windy_enabled:
            await self.windy.push_data_to_windy(data, False)

        # TODO: create ecowitt protocol to send full payload to Pocasi CZ
        if _pocasi_enabled:
            await self.pocasi.push_data_to_server(data, "WU")

        if health:
            health.update_forwarding(self.windy, self.pocasi)

        if checked_or(self.config.options.get(DEV_DBG), bool, False):
            _LOGGER.info("Dev log (ecowitt): %s", anonymize(data))

        return aiohttp.web.Response(body="OK", status=200)

    async def received_data(self, webdata: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle incoming webhook payload from the station.

        - validates authentication (different keys for WU vs WSLink)
        - optionally forwards data to third-party services (Windy / Pocasi)
        - remaps payload keys to internal sensor keys
        - auto-discovers new sensor fields and adds entities dynamically
        - updates coordinator data so existing entities refresh immediately
        """

        # WSLink uses different auth and payload field naming than the legacy endpoint.
        _wslink: bool = checked_or(self.config.options.get(WSLINK), bool, False)

        get_data = webdata.query
        post_data = await webdata.post()
        data: dict[str, Any] = {**dict(get_data), **dict(post_data)}

        health = self._health_coordinator()

        if not _wslink and ("ID" not in data or "PASSWORD" not in data):
            _LOGGER.error("Invalid request. No security data provided!")
            if health:
                health.update_ingress_result(
                    webdata,
                    accepted=False,
                    authorized=False,
                    reason="missing_credentials",
                )
            raise HTTPUnauthorized

        if _wslink and ("wsid" not in data or "wspw" not in data):
            _LOGGER.error("Invalid request. No security data provided!")
            if health:
                health.update_ingress_result(
                    webdata,
                    accepted=False,
                    authorized=False,
                    reason="missing_credentials",
                )
            raise HTTPUnauthorized

        if _wslink:
            id_data = data.get("wsid", "")
            key_data = data.get("wspw", "")
        else:
            id_data = data.get("ID", "")
            key_data = data.get("PASSWORD", "")

        if (_id := checked(self.config.options.get(API_ID), str)) is None:
            _LOGGER.error("We don't have API ID set! Update your config!")
            if health:
                health.update_ingress_result(
                    webdata,
                    accepted=False,
                    authorized=None,
                    reason="config_missing_api_id",
                )
            raise IncorrectDataError

        if (_key := checked(self.config.options.get(API_KEY), str)) is None:
            _LOGGER.error("We don't have API KEY set! Update your config!")
            if health:
                health.update_ingress_result(
                    webdata,
                    accepted=False,
                    authorized=None,
                    reason="config_missing_api_key",
                )
            raise IncorrectDataError

        # Constant-time comparison to avoid leaking credential length/content via timing.
        # Both operands are compared even if the first fails, so the branch order doesn't
        # short-circuit. Encode to bytes so non-ASCII credentials are handled safely.
        id_ok = hmac.compare_digest(id_data.encode("utf-8"), _id.encode("utf-8"))
        key_ok = hmac.compare_digest(key_data.encode("utf-8"), _key.encode("utf-8"))
        if not (id_ok & key_ok):
            _LOGGER.error("Unauthorised access!")
            if health:
                health.update_ingress_result(
                    webdata,
                    accepted=False,
                    authorized=False,
                    reason="unauthorized",
                )
            raise HTTPUnauthorized

        remaped_items: dict[str, str] = remap_wslink_items(data) if _wslink else remap_items(data)

        if sensors := check_disabled(remaped_items, self.config):
            if (
                translate_sensors := checked(
                    [
                        await translations(
                            self.hass,
                            DOMAIN,
                            f"sensor.{t_key}",
                            key="name",
                            category="entity",
                        )
                        for t_key in sensors
                        if await translations(
                            self.hass,
                            DOMAIN,
                            f"sensor.{t_key}",
                            key="name",
                            category="entity",
                        )
                        is not None
                    ],
                    list[str],
                )
            ) is not None:
                human_readable: str = "\n".join(translate_sensors)
            else:
                human_readable = ""

            await translated_notification(
                self.hass,
                DOMAIN,
                "added",
                {"added_sensors": f"{human_readable}\n"},
            )

            newly_discovered = list(sensors)

            if _loaded_sensors := loaded_sensors(self.config):
                sensors.extend(_loaded_sensors)
            await update_options(self.hass, self.config, SENSORS_TO_LOAD, sensors)

            # Dynamic adds avoid the listener-drop window of a full reload.
            add_new_sensors(self.hass, self.config, newly_discovered)
            add_new_binary_sensors(self.hass, self.config, newly_discovered)

        self.async_set_updated_data(remaped_items)
        if health:
            health.update_ingress_result(
                webdata,
                accepted=True,
                authorized=True,
                reason="accepted",
            )

        _windy_enabled = checked_or(self.config.options.get(WINDY_ENABLED), bool, False)
        _pocasi_enabled = checked_or(self.config.options.get(POCASI_CZ_ENABLED), bool, False)

        if _windy_enabled:
            await self.windy.push_data_to_windy(data, _wslink)

        if _pocasi_enabled:
            await self.pocasi.push_data_to_server(data, "WSLINK" if _wslink else "WU")

        if health:
            health.update_forwarding(self.windy, self.pocasi)

        if checked_or(self.config.options.get(DEV_DBG), bool, False):
            _LOGGER.info("Dev log: %s", anonymize(data))

        return aiohttp.web.Response(body="OK", status=200)
