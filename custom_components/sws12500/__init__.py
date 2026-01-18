"""The Sencor SWS 12500 Weather Station integration."""

import logging
from typing import Any

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
    DEV_DBG,
    DOMAIN,
    POCASI_CZ_ENABLED,
    SENSORS_TO_LOAD,
    WINDY_ENABLED,
    WSLINK,
    WSLINK_URL,
)
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


class WeatherDataUpdateCoordinator(DataUpdateCoordinator):
    """Manage fetched data."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Init global updater."""
        self.hass: HomeAssistant = hass
        self.config: ConfigEntry = config
        self.windy: WindyPush = WindyPush(hass, config)
        self.pocasi: PocasiPush = PocasiPush(hass, config)
        super().__init__(hass, _LOGGER, name=DOMAIN)

    async def recieved_data(self, webdata: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle incoming data query."""

        _wslink: bool = checked_or(self.config.options.get(WSLINK), bool, False)

        data: dict[str, Any] = dict(webdata.query)

        # Check if station is sending auth data
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

        # Check if we have valid auth data in the integration

        if (_id := checked(self.config.options.get(API_ID), str)) is None:
            _LOGGER.error("We don't have API ID set! Update your config!")
            raise IncorrectDataError

        if (_key := checked(self.config.options.get(API_KEY), str)) is None:
            _LOGGER.error("We don't have API KEY set! Update your config!")
            raise IncorrectDataError

        if id_data != _id or key_data != _key:
            _LOGGER.error("Unauthorised access!")
            raise HTTPUnauthorized

        if self.config.options.get(WINDY_ENABLED, False):
            await self.windy.push_data_to_windy(data)

        if self.config.options.get(POCASI_CZ_ENABLED, False):
            await self.pocasi.push_data_to_server(data, "WSLINK" if _wslink else "WU")

        remaped_items: dict[str, str] = (
            remap_wslink_items(data) if _wslink else remap_items(data)
        )

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
            if _loaded_sensors := loaded_sensors(self.config_entry):
                sensors.extend(_loaded_sensors)
            await update_options(self.hass, self.config_entry, SENSORS_TO_LOAD, sensors)
            # await self.hass.config_entries.async_reload(self.config.entry_id)

        self.async_set_updated_data(remaped_items)

        if self.config_entry.options.get(DEV_DBG):
            _LOGGER.info("Dev log: %s", anonymize(data))

        return aiohttp.web.Response(body="OK", status=200)


def register_path(
    hass: HomeAssistant,
    coordinator: WeatherDataUpdateCoordinator,
    config: ConfigEntry,
) -> bool:
    """Register paths to webhook."""

    hass.data.setdefault(DOMAIN, {})
    if (hass_data := checked(hass.data[DOMAIN], dict[str, Any])) is None:
        raise ConfigEntryNotReady

    _wslink: bool = checked_or(config.options.get(WSLINK), bool, False)

    # Create internal route dispatcher with provided urls
    routes: Routes = Routes()
    routes.add_route(DEFAULT_URL, coordinator.recieved_data, enabled=not _wslink)
    routes.add_route(WSLINK_URL, coordinator.recieved_data, enabled=_wslink)

    # Register webhooks in HomeAssistant with dispatcher
    try:
        _ = hass.http.app.router.add_get(DEFAULT_URL, routes.dispatch)
        _ = hass.http.app.router.add_get(WSLINK_URL, routes.dispatch)

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
    """Set up the config entry for my device."""

    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    hass_data = hass.data.setdefault(DOMAIN, {})
    hass_data[entry.entry_id] = coordinator

    routes: Routes | None = hass_data.get("routes", None)

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
    """Update setup listener."""

    _ = await hass.config_entries.async_reload(entry.entry_id)

    _LOGGER.info("Settings updated")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    _ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if _ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return _ok
