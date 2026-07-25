"""Sencor SWS 12500 Weather Station integration (push/webhook based).

Architecture overview
---------------------
This integration is *push-based*: the weather station calls our HTTP endpoint and we
receive an HTTP payload. We do not poll the station.

Key building blocks:
- `WeatherDataUpdateCoordinator` acts as an in-memory "data bus" for the latest payload.
  On each webhook request we call `async_set_updated_data(...)` and all `CoordinatorEntity`
  sensors get notified and update their states.
- `entry.runtime_data` stores per-entry runtime state (coordinator instance, options
  snapshot, and sensor platform callbacks). Shared aiohttp route registrations stay
  under `hass.data[DOMAIN]["routes"]` because they must survive a config-entry reload.

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

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from py_typecheck import checked, checked_or

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval

from .conflicts import effective_protocols, update_protocol_conflict_issue
from .const import (
    DEFAULT_URL,
    DOMAIN,
    ECOWITT_URL_PREFIX,
    HEALTH_URL,
    POCASI_CZ_ENABLED,
    POCASI_CZ_ENABLED_LEGACY,
    SENSORS_TO_LOAD,
    WINDY_ENABLED,
    WSLINK,
    WSLINK_URL,
)
from .coordinator import WeatherDataUpdateCoordinator
from .data import SWSConfigEntry, SWSRuntimeData
from .health_coordinator import HealthCoordinator
from .legacy import update_legacy_battery_issue
from .routes import Routes
from .staleness import update_stale_sensors_issue

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Keep in sync with `ConfigFlowHandler.VERSION`.
CONFIG_ENTRY_VERSION: int = 2


async def async_migrate_entry(hass: HomeAssistant, entry: SWSConfigEntry) -> bool:
    """Migrate an old config entry.

    Version 2 renames the Pocasi Meteo enable flag from the misspelled
    `pocasi_enabled_chcekbox` to `pocasi_enabled_checkbox`. Without moving the persisted
    value, forwarding would silently switch off for every existing install.
    """

    if entry.version > CONFIG_ENTRY_VERSION:
        # Downgrades are not supported - the entry was written by a newer version.
        return False

    if entry.version < 2:
        options = dict(entry.options)
        if POCASI_CZ_ENABLED_LEGACY in options:
            legacy_value = options.pop(POCASI_CZ_ENABLED_LEGACY)
            # Never clobber an already-correct key (both may exist after a partial upgrade).
            options.setdefault(POCASI_CZ_ENABLED, legacy_value)
            _LOGGER.debug("Migrated Pocasi Meteo enable flag to %s.", POCASI_CZ_ENABLED)

        hass.config_entries.async_update_entry(entry, options=options, version=2)

    return True


def register_path(
    hass: HomeAssistant,
    coordinator: WeatherDataUpdateCoordinator,
    coordinator_h: HealthCoordinator,
    config: SWSConfigEntry,
) -> bool:
    """Register webhook paths.

    We register the supported station endpoints and use an internal dispatcher
    (`Routes`) to enable only the configured ingress path. This lets us toggle
    protocols without re-registering routes on the aiohttp router.
    """

    hass.data.setdefault(DOMAIN, {})
    if (hass_data := checked(hass.data[DOMAIN], dict[str, Any])) is None:
        raise ConfigEntryNotReady

    _wslink: bool = checked_or(config.options.get(WSLINK), bool, False)
    # Legacy and Ecowitt share one entity namespace, so only one may be wired up.
    _legacy, _ecowitt_enabled = effective_protocols(config)

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
        routes.add_route(DEFAULT_URL, _default_route, coordinator.received_data, enabled=_legacy and not _wslink)
        routes.add_route(WSLINK_URL, _wslink_post_route, coordinator.received_data, enabled=_legacy and _wslink)
        routes.add_route(WSLINK_URL, _wslink_get_route, coordinator.received_data, enabled=_legacy and _wslink)

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
            coordinator.received_ecowitt_data,
            enabled=_ecowitt_enabled,
            sticky=True,
        )
    else:
        routes.activate()
        routes.set_ingress_observer(coordinator_h.record_dispatch)
        _LOGGER.info("We have already registered routes: %s", routes.show_enabled())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SWSConfigEntry) -> bool:
    """Set up a config entry.

    Per-entry state is held on `entry.runtime_data`. Only the shared aiohttp route dispatcher
    lives in `hass.data[DOMAIN]` because it must outlive a single entry reload. This separation is critical
    to avoid issues where entities stop receiving updates after a reload because the coordinator instance they
    are subscribed to is replaced in `hass.data[DOMAIN]` but the aiohttp route dispatcher still calls the old instance.
    """

    hass.data.setdefault(DOMAIN, {})

    coordinator = WeatherDataUpdateCoordinator(hass, entry)
    coordinator_health = HealthCoordinator(hass, entry)

    entry.runtime_data = SWSRuntimeData(
        coordinator=coordinator,
        health_coordinator=coordinator_health,
        last_options=dict(entry.options),
    )
    _wslink = checked_or(entry.options.get(WSLINK), bool, False)
    # Legacy and Ecowitt share one entity namespace, so only one may be wired up.
    _legacy, _ecowitt_enabled = effective_protocols(entry)
    _ecowitt_path = ECOWITT_URL_PREFIX + "/{webhook_id}"

    _LOGGER.debug("WS Link is %s", "enabled" if _wslink else "disabled")

    routes: Routes | None = hass.data[DOMAIN].get("routes")

    if routes is not None:
        _LOGGER.debug("We have routes registered, will try to switch dispatcher.")
        routes.activate()
        routes.switch_route(coordinator.received_data, DEFAULT_URL if not _wslink else WSLINK_URL, enabled=_legacy)
        routes.set_ecowitt_enabled(_ecowitt_path, coordinator.received_ecowitt_data, _ecowitt_enabled)
        # Rebind the sticky health route to the new coordinator so /station/health
        # does not keep serving the previous (stale) HealthCoordinator after a reload.
        routes.rebind_handler(HEALTH_URL, coordinator_health.health_status)
        routes.set_ingress_observer(coordinator_health.record_dispatch)
        coordinator_health.update_routing(routes)
        _LOGGER.debug("%s", routes.show_enabled())
    else:
        if not register_path(hass, coordinator, coordinator_health, entry):
            _LOGGER.error("Fatal: path not registered!")
            raise ConfigEntryNotReady("Webhook routes could not be registered")

        routes = hass.data[DOMAIN].get("routes")
        if routes is not None:
            coordinator_health.update_routing(routes)

    await coordinator_health.async_config_entry_first_refresh()
    coordinator_health.update_forwarding(coordinator.windy, coordinator.pocasi)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _check_stale(_now: datetime) -> None:
        update_stale_sensors_issue(hass, entry)

    entry.async_on_unload(async_track_time_interval(hass, _check_stale, timedelta(hours=1)))

    entry.async_on_unload(entry.add_update_listener(update_listener))
    update_legacy_battery_issue(hass, entry)
    update_protocol_conflict_issue(hass, entry)

    return True


async def update_listener(hass: HomeAssistant, entry: SWSConfigEntry):
    """Handle config entry option updates.

    We skip reloading when only live-read options change:
    - `SENSORS_TO_LOAD` (auto-discovery updates it as new payload fields appear), and
    - the forwarding enable flags (`WINDY_ENABLED`/`POCASI_CZ_ENABLED`), which the
      forwarders read on every push - so a forwarder that auto-disables itself from the
      hot path no longer triggers a disruptive reload.

    Why:
    - Reloading a push-based integration temporarily unloads platforms and removes
      coordinator listeners, which can make the UI appear "stuck" until restart.
    """

    runtime = getattr(entry, "runtime_data", None)
    if isinstance(runtime, SWSRuntimeData):
        old_options = runtime.last_options
        new_options = dict(entry.options)

        changed_keys = {k for k in set(old_options) | set(new_options) if old_options.get(k) != new_options.get(k)}

        runtime.last_options = new_options

        if changed_keys and changed_keys <= {SENSORS_TO_LOAD, WINDY_ENABLED, POCASI_CZ_ENABLED}:
            _LOGGER.debug("Options updated (%s); skipping reload.", ", ".join(sorted(changed_keys)))
            return

    update_legacy_battery_issue(hass, entry)
    await hass.config_entries.async_reload(entry.entry_id)
    _LOGGER.info("Settings updated")


async def async_unload_entry(hass: HomeAssistant, entry: SWSConfigEntry) -> bool:
    """Unload a config entry.

    `entry.runtime_data` becomes irrelevant once entry is unloaded.
    On next `async_setup_entry` we overwrite it. The shared `hass.data[DOMAIN]["routes"]` survives by design.
    aiohttp routes stay registered and the dispatcher is re-wired on the next setup.
    """

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        domain_data = hass.data.get(DOMAIN)
        routes = domain_data.get("routes") if isinstance(domain_data, dict) else None
        if isinstance(routes, Routes):
            routes.deactivate()
        setattr(entry, "runtime_data", None)

    return unload_ok
