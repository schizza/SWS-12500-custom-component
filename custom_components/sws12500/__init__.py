"""Sencor SWS 12500 Weather Station integration (push/webhook based).

Architecture overview
---------------------
This integration is *push-based*: the weather station calls our HTTP endpoint and we
receive a query payload. We do not poll the station.

Key building blocks:
- `WeatherDataUpdateCoordinator` acts as an in-memory "data bus" for the latest payload.
  On each webhook request we call `async_set_updated_data(...)` and all `CoordinatorEntity`
  sensors get notified and update their states.
- `hass.data[DOMAIN][entry_id]` is a per-entry *dict* that stores runtime state
  (coordinator instance, options snapshot, and sensor platform callbacks). Keeping this
  structure consistent is critical; mixing different value types under the same key can
  break listener wiring and make the UI appear "frozen".

Auto-discovery
--------------
When the station starts sending a new field, we:
1) persist the new sensor key into options (`SENSORS_TO_LOAD`)
2) dynamically add the new entity through the sensor platform (without reloading)

Why avoid reload?
Reloading a config entry unloads platforms temporarily, which removes coordinator listeners.
With a high-frequency push source (webhook), a reload at the wrong moment can lead to a
period where no entities are subscribed, causing stale states until another full reload/restart.
"""

import logging
from typing import Any

import aiohttp.web
from aiohttp.web_exceptions import HTTPUnauthorized
from py_typecheck import checked, checked_or

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, InvalidStateError, PlatformNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    API_ID,
    API_KEY,
    DEFAULT_URL,
    DEV_DBG,
    DOMAIN,
    ECOWITT_ENABLED,
    ECOWITT_URL_PREFIX,
    HEALTH_URL,
    POCASI_CZ_ENABLED,
    SENSORS_TO_LOAD,
    WINDY_ENABLED,
    WSLINK,
    WSLINK_URL,
)
from .data import ENTRY_COORDINATOR, ENTRY_HEALTH_COORD, ENTRY_LAST_OPTIONS
from .ecowitt import EcowittBridge  # noqa: PLC0415
from .health_coordinator import HealthCoordinator
from .pocasti_cz import PocasiPush
from .routes import Routes
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
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


class IncorrectDataError(InvalidStateError):
    """Invalid exception."""


# NOTE:
# We intentionally avoid importing the sensor platform module at import-time here.
# Home Assistant can import modules in different orders; keeping imports acyclic
# prevents "partially initialized module" failures (circular imports / partially initialized modules).
#
# When we need to dynamically add sensors, we do a local import inside the webhook handler.


class WeatherDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator for push updates.

    Even though Home Assistant's `DataUpdateCoordinator` is often used for polling,
    it also works well as a "fan-out" mechanism for push integrations:
    - webhook handler updates `self.data` via `async_set_updated_data`
    - all `CoordinatorEntity` instances subscribed to this coordinator update themselves
    """

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Initialize the coordinator.

        `config` is the config entry for this integration instance. We store it because
        the webhook handler needs access to options (auth data, enabled features, etc.).
        """
        self.hass: HomeAssistant = hass
        self.config: ConfigEntry = config
        self.windy: WindyPush = WindyPush(hass, config)
        self.pocasi: PocasiPush = PocasiPush(hass, config)

        # Ecowitt bridge - aioecowitt parser without HTTP server

        self.ecowitt_bridge: EcowittBridge = EcowittBridge(hass, config)

        super().__init__(hass, _LOGGER, name=DOMAIN)

    def _health_coordinator(self) -> HealthCoordinator | None:
        """Return the health coordinator for this config entry."""
        if (data := checked(self.hass.data.get(DOMAIN), dict[str, Any])) is None:
            return None
        if (entry := checked(data.get(self.config.entry_id), dict[str, Any])) is None:
            return None

        coordinator = entry.get(ENTRY_HEALTH_COORD)
        return coordinator if isinstance(coordinator, HealthCoordinator) else None

    async def recieved_ecowitt_data(self, webdata: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle incoming Ecowitt webhook payload.

        We are using aioecowitt for parsing payload. Sensors with internal
        mapping will use SWS pipline. Sensors withou mapping will create
        native Ecowitt entity trough bridge callback.
        """

        from .const import ECOWITT_ENABLED, ECOWITT_WEBHOOK_ID  # noqa: PLC0415

        health = self._health_coordinator()

        # Do we have Ecowitt enabled?
        if not checked_or(self.config.options.get(ECOWITT_ENABLED), bool, False):
            if health:
                health.update_ingress_result(
                    webdata,
                    accepted=False,
                    authorized=None,
                    reason="ecowitt_disabled",
                )
            return aiohttp.web.Response(text="Ecowitt disabled", status=403)

        # Check webhook ID from URL
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

        # Parse POST body
        post_data = await webdata.post()
        data: dict[str, Any] = dict(post_data)

        # Bridge: aioecowitt parsing + internal remap
        mapped_data = await self.ecowitt_bridge.process_payload(data)

        # Mapped sensors to SWS pipline (auto-discovery + fan-out)
        if mapped_data:
            if sensors := check_disabled(mapped_data, self.config):
                newly_discovered = list(sensors)
                if _loaded_senosrs := loaded_sensors(self.config):
                    sensors.extend(_loaded_senosrs)
                await update_options(self.hass, self.config, SENSORS_TO_LOAD, sensors)

                from .binary_sensor import add_new_binary_sensors  # noqa: PLC0415
                from .sensor import add_new_sensors  # noqa: PLC0415

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

        # Forwarding (mapped data in WU units)
        _windy_enabled = checked_or(self.config.options.get(WINDY_ENABLED), bool, False)
        _pocasi_enabled = checked_or(self.config.options.get(POCASI_CZ_ENABLED), bool, False)
        if _windy_enabled:
            await self.windy.push_data_to_windy(data, False)

        # Will push just WU payload to POCASI
        # TODO: create ecowitt protocol to send full payload to Pocasi CZ
        if _pocasi_enabled:
            await self.pocasi.push_data_to_server(data, "WU")

        if health:
            health.update_forwarding(self.windy, self.pocasi)

        if (_ := checked(self.config.options.get(DEV_DBG), True)) is not None:
            _LOGGER.info("Dev log (ecowitt): %s", anonymize(data))

        return aiohttp.web.Response(body="OK", status=200)

    async def received_data(self, webdata: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle incoming webhook payload from the station.

        This method:
        - validates authentication (different keys for WU vs WSLink)
        - optionally forwards data to third-party services (Windy / Pocasi)
        - remaps payload keys to internal sensor keys
        - auto-discovers new sensor fields and adds entities dynamically
        - updates coordinator data so existing entities refresh immediately
        """

        # WSLink uses different auth and payload field naming than the legacy endpoint.
        _wslink: bool = checked_or(self.config.options.get(WSLINK), bool, False)

        # Incoming station payload is delivered as query params.
        # Some stations posts data in body, so we need to contracts those data.
        #
        # We copy it to a plain dict so it can be passed around safely.
        get_data = webdata.query
        post_data = await webdata.post()

        # normalize incoming data to dict[str, Any]
        data: dict[str, Any] = {**dict(get_data), **dict(post_data)}

        # Get health data coordinator
        health = self._health_coordinator()

        # Validate auth keys (different parameter names depending on endpoint mode).
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

        id_data: str = ""
        key_data: str = ""

        if _wslink:
            id_data = data.get("wsid", "")
            key_data = data.get("wspw", "")
        else:
            id_data = data.get("ID", "")
            key_data = data.get("PASSWORD", "")

        # Validate credentials against the integration's configured options.
        # If auth doesn't match, we reject the request (prevents random pushes from the LAN/Internet).

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

        if id_data != _id or key_data != _key:
            _LOGGER.error("Unauthorised access!")
            if health:
                health.update_ingress_result(
                    webdata,
                    accepted=False,
                    authorized=False,
                    reason="unauthorized",
                )
            raise HTTPUnauthorized

        # Convert raw payload keys to our internal sensor keys (stable identifiers).
        remaped_items: dict[str, str] = remap_wslink_items(data) if _wslink else remap_items(data)

        # Auto-discovery: if payload contains keys that are not enabled/loaded yet,
        # add them to the option list and create entities dynamically.
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

            # Persist newly discovered sensor keys to options (so they remain enabled after restart).
            newly_discovered = list(sensors)

            if _loaded_sensors := loaded_sensors(self.config):
                sensors.extend(_loaded_sensors)
            await update_options(self.hass, self.config, SENSORS_TO_LOAD, sensors)

            # Dynamically add newly discovered sensors *without* reloading the entry.
            #
            # Why: Reloading a config entry unloads platforms temporarily. That removes coordinator
            # listeners; with frequent webhook pushes the UI can appear "frozen" until the listeners
            # are re-established. Dynamic adds avoid this window completely.
            #
            # We do a local import to avoid circular imports at module import time.
            #
            # NOTE: Some linters prefer top-level imports. In this case the local import is
            # intentional and prevents "partially initialized module" errors.

            from .binary_sensor import add_new_binary_sensors  # noqa: PLC0415 (local import is intentional)
            from .sensor import add_new_sensors  # noqa: PLC0415 (local import is intentional)

            add_new_sensors(self.hass, self.config, newly_discovered)
            add_new_binary_sensors(self.hass, self.config, newly_discovered)

        # Fan-out update: notify all subscribed entities.
        self.async_set_updated_data(remaped_items)
        if health:
            health.update_ingress_result(
                webdata,
                accepted=True,
                authorized=True,
                reason="accepted",
            )

        # Optional forwarding to external services. This is kept here (in the webhook handler)
        # to avoid additional background polling tasks.

        _windy_enabled = checked_or(self.config.options.get(WINDY_ENABLED), bool, False)
        _pocasi_enabled = checked_or(self.config.options.get(POCASI_CZ_ENABLED), bool, False)

        if _windy_enabled:
            await self.windy.push_data_to_windy(data, _wslink)

        if _pocasi_enabled:
            await self.pocasi.push_data_to_server(data, "WSLINK" if _wslink else "WU")

        if health:
            health.update_forwarding(self.windy, self.pocasi)

        # Optional dev logging (keep it lightweight to avoid log spam under high-frequency updates).
        if self.config.options.get("dev_debug_checkbox"):
            _LOGGER.info("Dev log: %s", anonymize(data))

        return aiohttp.web.Response(body="OK", status=200)


def register_path(
    hass: HomeAssistant,
    coordinator: WeatherDataUpdateCoordinator,
    coordinator_h: HealthCoordinator,
    config: ConfigEntry,
) -> bool:
    """Register webhook paths.

    We register both possible endpoints and use an internal dispatcher (`Routes`) to
    enable exactly one of them. This lets us toggle WSLink mode without re-registering
    routes on the aiohttp router.
    """

    hass.data.setdefault(DOMAIN, {})
    if (hass_data := checked(hass.data[DOMAIN], dict[str, Any])) is None:
        raise ConfigEntryNotReady

    _wslink: bool = checked_or(config.options.get(WSLINK), bool, False)
    _ecowitt_enabled: bool = checked_or(config.options.get(ECOWITT_ENABLED), bool, False)

    # Load registred routes
    routes: Routes | None = hass_data.get("routes", None)

    if not isinstance(routes, Routes):
        routes = Routes()
        routes.set_ingress_observer(coordinator_h.record_dispatch)

        # Register webhooks in HomeAssistant with dispatcher
        try:
            _default_route = hass.http.app.router.add_get(DEFAULT_URL, routes.dispatch, name="_default_route")
            _wslink_post_route = hass.http.app.router.add_post(WSLINK_URL, routes.dispatch, name="_wslink_post_route")
            _wslink_get_route = hass.http.app.router.add_get(WSLINK_URL, routes.dispatch, name="_wslink_get_route")
            _health_route = hass.http.app.router.add_get(HEALTH_URL, routes.dispatch, name="_health_route")

            # Ecowitt URL contains {webhook_id} as a parameter.
            # Station is configured to send data to: http://ha:8123/weatherhub/<webhook_id>

            _ecowitt_path = ECOWITT_URL_PREFIX + "/{webhook_id}"
            _ecowitt_route = hass.http.app.router.add_post(_ecowitt_path, routes.dispatch, name="_ecowitt_route")

            # Save initialised routes
            hass_data["routes"] = routes

        except RuntimeError as Ex:
            _LOGGER.critical("Routes cannot be added. Integration will not work as expected. %s", Ex)
            raise ConfigEntryNotReady from Ex

        # Finally create internal route dispatcher with provided urls, while we have webhooks registered.
        routes.add_route(DEFAULT_URL, _default_route, coordinator.received_data, enabled=not _wslink)
        routes.add_route(WSLINK_URL, _wslink_post_route, coordinator.received_data, enabled=_wslink)
        routes.add_route(WSLINK_URL, _wslink_get_route, coordinator.received_data, enabled=_wslink)
        # Make health route `sticky` so it will not change upon updating options.
        routes.add_route(
            HEALTH_URL,
            _health_route,
            coordinator_h.health_status,
            enabled=True,
            sticky=True,
        )
        routes.add_route(
            _ecowitt_path,
            _ecowitt_route,
            coordinator.recieved_ecowitt_data,
            enabled=_ecowitt_enabled,
            sticky=True,
        )
    else:
        routes.set_ingress_observer(coordinator_h.record_dispatch)
        _LOGGER.info("We have already registered routes: %s", routes.show_enabled())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry.

    Important:
    - We store per-entry runtime state under `hass.data[DOMAIN][entry_id]` as a dict.
    - We reuse the same coordinator instance across reloads so that:
      - the webhook handler keeps updating the same coordinator
      - already-created entities remain subscribed

    """

    hass_data = hass.data.setdefault(DOMAIN, {})
    # hass_data = cast("dict[str, Any]", hass_data_any)

    # Per-entry runtime storage:
    # hass.data[DOMAIN][entry_id] is always a dict (never the coordinator itself).
    # Mixing types here (sometimes dict, sometimes coordinator) is a common source of hard-to-debug
    # issues where entities stop receiving updates.

    if (entry_data := checked(hass_data.get(entry.entry_id), dict[str, Any])) is None:
        entry_data = {}
    hass_data[entry.entry_id] = entry_data

    # Reuse the existing coordinator across reloads so webhook handlers and entities
    # remain connected to the same coordinator instance.
    #
    # Note: Routes store a bound method (`coordinator.received_data`). If we replaced the coordinator
    # instance on reload, the dispatcher could keep calling the old instance while entities listen
    # to the new one, causing updates to "disappear".
    coordinator = entry_data.get(ENTRY_COORDINATOR)
    if isinstance(coordinator, WeatherDataUpdateCoordinator):
        coordinator.config = entry

        # Recreate helper instances so they pick up updated options safely.
        coordinator.windy = WindyPush(hass, entry)
        coordinator.pocasi = PocasiPush(hass, entry)
    else:
        coordinator = WeatherDataUpdateCoordinator(hass, entry)
        entry_data[ENTRY_COORDINATOR] = coordinator

    # Similar to the coordinator, we want to reuse the same health coordinator instance across
    # reloads so that the health endpoint remains responsive and doesn't lose its listeners.
    coordinator_health = entry_data.get(ENTRY_HEALTH_COORD)
    if isinstance(coordinator_health, HealthCoordinator):
        coordinator_health.config = entry
    else:
        coordinator_health = HealthCoordinator(hass, entry)
        entry_data[ENTRY_HEALTH_COORD] = coordinator_health

    routes: Routes | None = hass_data.get("routes", None)

    # Keep an options snapshot so update_listener can skip reloads when only `SENSORS_TO_LOAD` changes.
    # Auto-discovery updates this option frequently and we do not want to reload for that case.
    entry_data[ENTRY_LAST_OPTIONS] = dict(entry.options)

    _wslink = checked_or(entry.options.get(WSLINK), bool, False)
    _ecowitt_enabled = checked_or(entry.options.get(ECOWITT_ENABLED), bool, False)
    _ecowitt_path = ECOWITT_URL_PREFIX + "/{webhook_id}"

    _LOGGER.debug("WS Link is %s", "enabled" if _wslink else "disabled")

    if routes:
        _LOGGER.debug("We have routes registered, will try to switch dispatcher.")
        routes.switch_route(coordinator.received_data, DEFAULT_URL if not _wslink else WSLINK_URL)
        routes.set_ecowitt_enabled(_ecowitt_path, coordinator.recieved_ecowitt_data, _ecowitt_enabled)
        routes.set_ingress_observer(coordinator_health.record_dispatch)
        coordinator_health.update_routing(routes)
        _LOGGER.debug("%s", routes.show_enabled())
    else:
        routes_enabled = register_path(hass, coordinator, coordinator_health, entry)

        if not routes_enabled:
            _LOGGER.error("Fatal: path not registered!")
            raise PlatformNotReady
        routes = hass_data.get("routes", None)
        if isinstance(routes, Routes):
            coordinator_health.update_routing(routes)

    await coordinator_health.async_config_entry_first_refresh()
    coordinator_health.update_forwarding(coordinator.windy, coordinator.pocasi)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle config entry option updates.

    We skip reloading when only `SENSORS_TO_LOAD` changes.

    Why:
    - Auto-discovery updates `SENSORS_TO_LOAD` as new payload fields appear.
    - Reloading a push-based integration temporarily unloads platforms and removes
      coordinator listeners, which can make the UI appear "stuck" until restart.
    """

    if (hass_data := checked(hass.data.get(DOMAIN), dict[str, Any])) is not None:
        if (entry_data := checked(hass_data.get(entry.entry_id), dict[str, Any])) is not None:
            if (old_options := checked(entry_data.get(ENTRY_LAST_OPTIONS), dict[str, Any])) is not None:
                new_options = dict(entry.options)

                changed_keys = {
                    k
                    for k in set(old_options.keys()) | set(new_options.keys())
                    if old_options.get(k) != new_options.get(k)
                }

                # Update snapshot early for the next comparison.
                entry_data[ENTRY_LAST_OPTIONS] = new_options

                if changed_keys == {SENSORS_TO_LOAD}:
                    _LOGGER.debug("Options updated (%s); skipping reload.", SENSORS_TO_LOAD)
                    return
            else:
                # No/invalid snapshot: store current options for next comparison.
                entry_data[ENTRY_LAST_OPTIONS] = dict(entry.options)

    _ = await hass.config_entries.async_reload(entry.entry_id)
    _LOGGER.info("Settings updated")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    _ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if _ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return _ok
