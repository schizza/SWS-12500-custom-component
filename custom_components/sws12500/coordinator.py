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
from homeassistant.util import dt as dt_util

from .binary_sensor import add_new_binary_sensors
from .const import (
    API_ID,
    API_KEY,
    CH_HUMIDITY_TYPE_PARAM,
    CHANNEL_TYPES,
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
    channel_types,
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

        super().__init__(hass, _LOGGER, config_entry=config, name=DOMAIN)

    def _health_coordinator(self) -> HealthCoordinator | None:
        """Return the health coordinator for this config entry."""
        try:
            return self.config.runtime_data.health_coordinator
        except AttributeError:
            return None

    def _validate_credentials(
        self,
        data: dict[str, Any],
        webdata: aiohttp.web.Request,
        *,
        wslink: bool,
        health: HealthCoordinator | None,
    ) -> None:
        """Validate station credentials for the legacy / WSLink endpoint.

        Raises HTTPUnauthorized (missing/empty/wrong credentials) or IncorrectDataError
        (integration not configured); returns None on success.
        """
        id_key, pw_key = ("wsid", "wspw") if wslink else ("ID", "PASSWORD")

        if id_key not in data or pw_key not in data:
            _LOGGER.error("Invalid request. No security data provided!")
            if health:
                health.update_ingress_result(webdata, accepted=False, authorized=False, reason="missing_credentials")
            raise HTTPUnauthorized

        id_data = data.get(id_key, "")
        key_data = data.get(pw_key, "")

        if (_id := checked(self.config.options.get(API_ID), str)) is None:
            _LOGGER.error("We don't have API ID set! Update your config!")
            if health:
                health.update_ingress_result(webdata, accepted=False, authorized=None, reason="config_missing_api_id")
            raise IncorrectDataError

        if (_key := checked(self.config.options.get(API_KEY), str)) is None:
            _LOGGER.error("We don't have API KEY set! Update your config!")
            if health:
                health.update_ingress_result(webdata, accepted=False, authorized=None, reason="config_missing_api_key")
            raise IncorrectDataError

        # Defense-in-depth: reject empty configured/incoming credentials so this handler
        # is self-protecting regardless of how options were set.
        if not _id or not _key:
            _LOGGER.error("API ID/KEY is empty! Update your config!")
            if health:
                health.update_ingress_result(
                    webdata, accepted=False, authorized=None, reason="config_missing_credentials"
                )
            raise IncorrectDataError

        if not id_data or not key_data:
            _LOGGER.error("Unauthorised access! Empty credentials.")
            if health:
                health.update_ingress_result(webdata, accepted=False, authorized=False, reason="unauthorized")
            raise HTTPUnauthorized

        # Constant-time comparison; both operands are always compared (no short-circuit)
        # and encoded to bytes so non-ASCII credentials are handled safely.
        id_ok = hmac.compare_digest(id_data.encode("utf-8"), _id.encode("utf-8"))
        key_ok = hmac.compare_digest(key_data.encode("utf-8"), _key.encode("utf-8"))
        if not (id_ok & key_ok):
            _LOGGER.error("Unauthorised access!")
            if health:
                health.update_ingress_result(webdata, accepted=False, authorized=False, reason="unauthorized")
            raise HTTPUnauthorized

    async def received_ecowitt_data(self, webdata: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle incoming Ecowitt webhook payload.

        Uses aioecowitt for payload parsing. Sensors with internal mapping
        join the SWS pipeline; sensors without mapping create native Ecowitt
        entities through the bridge callback.
        """

        # See received_data: reject cleanly if the entry is mid-reload (no runtime_data).
        if getattr(self.config, "runtime_data", None) is None:
            return aiohttp.web.Response(text="Integration is reloading.", status=503)

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

        # Constant-time comparison to avoid leaking the webhook id via timing.
        if not expected_webhook or not hmac.compare_digest(
            actual_webhook.encode("utf-8"), expected_webhook.encode("utf-8")
        ):
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

        # Record the Ecowitt station model (used as the device model) before parsing,
        # so native entities created during process_payload report it.
        if model := checked(data.get("model"), str):
            self.config.runtime_data.ecowitt_model = model

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
            now = dt_util.utcnow()
            for key in mapped_data:
                self.config.runtime_data.last_seen[key] = now

        if health:
            health.update_ingress_result(
                webdata,
                accepted=True,
                authorized=True,
                reason="accepted",
            )

        _windy_enabled = checked_or(self.config.options.get(WINDY_ENABLED), bool, False)
        _pocasi_enabled = checked_or(self.config.options.get(POCASI_CZ_ENABLED), bool, False)

        # The two services need the payload in different shapes. Windy has no Ecowitt
        # endpoint and converts to PWS itself; Pocasi Meteo does, so it gets the station
        # payload verbatim.
        if _windy_enabled:
            await self.windy.push_data_to_windy(data, "ecowitt")

        # Pocasi Meteo does have an Ecowitt endpoint, so it gets the station payload
        # verbatim instead.
        if _pocasi_enabled:
            await self.pocasi.push_data_to_server(data, "ECOWITT")

        if health:
            health.update_forwarding(self.windy, self.pocasi)

        if checked_or(self.config.options.get(DEV_DBG), bool, False):
            _LOGGER.info("Dev log (ecowitt): %s", anonymize(data))

        return aiohttp.web.Response(body="OK", status=200)

    async def _persist_channel_types(self, data: dict[str, Any]) -> None:
        """Store the reported `t234cXtp` probe types in the config entry options.

        Entities are created during entry setup, before the first payload arrives, so
        the probe type that decides a channel's humidity device class has to outlive
        the current session - runtime state resets on every reload.

        Merged rather than replaced: a payload that omits some `tp` parameters says
        nothing about the channels it left out. Written only when something actually
        changed, and `update_listener` skips the reload for this key.
        """

        reported = {param: str(data[param]) for param in CH_HUMIDITY_TYPE_PARAM.values() if param in data}
        if not reported:
            return

        stored = channel_types(self.config)
        merged = {**stored, **reported}
        if merged != stored:
            await update_options(self.hass, self.config, CHANNEL_TYPES, merged)

    async def received_data(self, webdata: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle incoming webhook payload from the station.

        - validates authentication (different keys for WU vs WSLink)
        - optionally forwards data to third-party services (Windy / Pocasi)
        - remaps payload keys to internal sensor keys
        - auto-discovers new sensor fields and adds entities dynamically
        - updates coordinator data so existing entities refresh immediately
        """

        # The aiohttp routes outlive a config-entry reload and keep pointing at this
        # bound method. If a payload arrives while the entry is unloaded, runtime_data
        # is gone; reject cleanly with 503 instead of raising AttributeError (500).
        if getattr(self.config, "runtime_data", None) is None:
            return aiohttp.web.Response(text="Integration is reloading.", status=503)

        # WSLink uses different auth and payload field naming than the legacy endpoint.
        _wslink: bool = checked_or(self.config.options.get(WSLINK), bool, False)

        get_data = webdata.query
        post_data = await webdata.post()
        data: dict[str, Any] = {**dict(get_data), **dict(post_data)}

        health = self._health_coordinator()

        self._validate_credentials(data, webdata, wslink=_wslink, health=health)

        remaped_items: dict[str, str] = remap_wslink_items(data) if _wslink else remap_items(data)

        # The probe type per channel is not a reading, so it is not remapped - but a
        # sensor created later needs it to tell soil moisture from air humidity.
        if _wslink:
            await self._persist_channel_types(data)

        if sensors := check_disabled(remaped_items, self.config):
            # Resolve each sensor's display name once (the previous comprehension
            # awaited translations() twice per key).
            translated_sensors: list[str] = []
            for t_key in sensors:
                name = await translations(
                    self.hass,
                    DOMAIN,
                    f"sensor.{t_key}",
                    key="name",
                    category="entity",
                )
                if name is not None:
                    translated_sensors.append(name)

            human_readable = "\n".join(translated_sensors)

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

        now = dt_util.utcnow()
        for key in remaped_items:
            self.config.runtime_data.last_seen[key] = now

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
            await self.windy.push_data_to_windy(data, "wslink" if _wslink else "pws")

        if _pocasi_enabled:
            await self.pocasi.push_data_to_server(data, "WSLINK" if _wslink else "WU")

        if health:
            health.update_forwarding(self.windy, self.pocasi)

        if checked_or(self.config.options.get(DEV_DBG), bool, False):
            _LOGGER.info("Dev log: %s", anonymize(data))

        return aiohttp.web.Response(body="OK", status=200)
