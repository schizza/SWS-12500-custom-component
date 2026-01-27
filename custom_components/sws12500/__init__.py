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
from typing import Any, cast

import aiohttp.web
from aiohttp.web_exceptions import HTTPUnauthorized
from py_typecheck import checked, checked_or

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    InvalidStateError,
    PlatformNotReady,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    API_ID,
    API_KEY,
    DEFAULT_URL,
    DOMAIN,
    POCASI_CZ_ENABLED,
    SENSORS_TO_LOAD,
    WINDY_ENABLED,
    WSLINK,
    WSLINK_URL,
)
from .data import ENTRY_COORDINATOR, ENTRY_LAST_OPTIONS
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
PLATFORMS: list[Platform] = [Platform.SENSOR]


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
        super().__init__(hass, _LOGGER, name=DOMAIN)

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
        # We copy it to a plain dict so it can be passed around safely.
        data: dict[str, Any] = dict(webdata.query)

        # Validate auth keys (different parameter names depending on endpoint mode).
        if not _wslink and ("ID" not in data or "PASSWORD" not in data):
            _LOGGER.error("Invalid request. No security data provided!")
            raise HTTPUnauthorized

        if _wslink and ("wsid" not in data or "wspw" not in data):
            _LOGGER.error("Invalid request. No security data provided!")
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
            raise IncorrectDataError

        if (_key := checked(self.config.options.get(API_KEY), str)) is None:
            _LOGGER.error("We don't have API KEY set! Update your config!")
            raise IncorrectDataError

        if id_data != _id or key_data != _key:
            _LOGGER.error("Unauthorised access!")
            raise HTTPUnauthorized

        # Optional forwarding to external services. This is kept here (in the webhook handler)
        # to avoid additional background polling tasks.
        if self.config.options.get(WINDY_ENABLED, False):
            await self.windy.push_data_to_windy(data)

        if self.config.options.get(POCASI_CZ_ENABLED, False):
            await self.pocasi.push_data_to_server(data, "WSLINK" if _wslink else "WU")

        # Convert raw payload keys to our internal sensor keys (stable identifiers).
        remaped_items: dict[str, str] = (
            remap_wslink_items(data) if _wslink else remap_items(data)
        )

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

            from .sensor import (  # noqa: PLC0415 (local import is intentional)
                add_new_sensors,
            )

            add_new_sensors(self.hass, self.config, newly_discovered)

        # Fan-out update: notify all subscribed entities.
        self.async_set_updated_data(remaped_items)

        # Optional dev logging (keep it lightweight to avoid log spam under high-frequency updates).
        if self.config.options.get("dev_debug_checkbox"):
            _LOGGER.info("Dev log: %s", anonymize(data))

        return aiohttp.web.Response(body="OK", status=200)


def register_path(
    hass: HomeAssistant,
    coordinator: WeatherDataUpdateCoordinator,
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

    # Create internal route dispatcher with provided urls
    routes: Routes = Routes()
    routes.add_route(DEFAULT_URL, coordinator.received_data, enabled=not _wslink)
    routes.add_route(WSLINK_URL, coordinator.received_data, enabled=_wslink)

    # Register webhooks in HomeAssistant with dispatcher
    try:
        _ = hass.http.app.router.add_get(DEFAULT_URL, routes.dispatch)
        _ = hass.http.app.router.add_post(WSLINK_URL, routes.dispatch)

        # Save initialised routes
        hass_data["routes"] = routes

    except RuntimeError as Ex:
        _LOGGER.critical(
            "Routes cannot be added. Integration will not work as expected. %s", Ex
        )
        raise ConfigEntryNotReady from Ex
    else:
        return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry.

    Important:
    - We store per-entry runtime state under `hass.data[DOMAIN][entry_id]` as a dict.
    - We reuse the same coordinator instance across reloads so that:
      - the webhook handler keeps updating the same coordinator
      - already-created entities remain subscribed

    """

    hass_data_any = hass.data.setdefault(DOMAIN, {})
    hass_data = cast("dict[str, Any]", hass_data_any)

    # Per-entry runtime storage:
    # hass.data[DOMAIN][entry_id] is always a dict (never the coordinator itself).
    # Mixing types here (sometimes dict, sometimes coordinator) is a common source of hard-to-debug
    # issues where entities stop receiving updates.
    entry_data_any = hass_data.get(entry.entry_id)
    if not isinstance(entry_data_any, dict):
        entry_data_any = {}
        hass_data[entry.entry_id] = entry_data_any
    entry_data = cast("dict[str, Any]", entry_data_any)

    # Reuse the existing coordinator across reloads so webhook handlers and entities
    # remain connected to the same coordinator instance.
    #
    # Note: Routes store a bound method (`coordinator.received_data`). If we replaced the coordinator
    # instance on reload, the dispatcher could keep calling the old instance while entities listen
    # to the new one, causing updates to "disappear".
    coordinator_any = entry_data.get(ENTRY_COORDINATOR)
    if isinstance(coordinator_any, WeatherDataUpdateCoordinator):
        coordinator_any.config = entry

        # Recreate helper instances so they pick up updated options safely.
        coordinator_any.windy = WindyPush(hass, entry)
        coordinator_any.pocasi = PocasiPush(hass, entry)
        coordinator = coordinator_any
    else:
        coordinator = WeatherDataUpdateCoordinator(hass, entry)
        entry_data[ENTRY_COORDINATOR] = coordinator

    routes: Routes | None = hass_data.get("routes", None)

    # Keep an options snapshot so update_listener can skip reloads when only `SENSORS_TO_LOAD` changes.
    # Auto-discovery updates this option frequently and we do not want to reload for that case.
    entry_data[ENTRY_LAST_OPTIONS] = dict(entry.options)

    _wslink = checked_or(entry.options.get(WSLINK), bool, False)

    _LOGGER.debug("WS Link is %s", "enbled" if _wslink else "disabled")

    if routes:
        _LOGGER.debug("We have routes registered, will try to switch dispatcher.")
        routes.switch_route(DEFAULT_URL if not _wslink else WSLINK_URL)
        _LOGGER.debug("%s", routes.show_enabled())
    else:
        routes_enabled = register_path(hass, coordinator, entry)

        if not routes_enabled:
            _LOGGER.error("Fatal: path not registered!")
            raise PlatformNotReady

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
    hass_data_any = hass.data.get(DOMAIN)
    if isinstance(hass_data_any, dict):
        hass_data = cast("dict[str, Any]", hass_data_any)
        entry_data_any = hass_data.get(entry.entry_id)
        if isinstance(entry_data_any, dict):
            entry_data = cast("dict[str, Any]", entry_data_any)

            old_options_any = entry_data.get(ENTRY_LAST_OPTIONS)
            if isinstance(old_options_any, dict):
                old_options = cast("dict[str, Any]", old_options_any)
                new_options = dict(entry.options)

                changed_keys = {
                    k
                    for k in set(old_options.keys()) | set(new_options.keys())
                    if old_options.get(k) != new_options.get(k)
                }

                # Update snapshot early for the next comparison.
                entry_data[ENTRY_LAST_OPTIONS] = new_options

                if changed_keys == {SENSORS_TO_LOAD}:
                    _LOGGER.debug(
                        "Options updated (%s); skipping reload.", SENSORS_TO_LOAD
                    )
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
