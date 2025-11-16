"""The Sencor SWS 12500 Weather Station integration."""

import logging

import aiohttp.web
from aiohttp.web_exceptions import HTTPUnauthorized

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import InvalidStateError, PlatformNotReady
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
from .routes import Routes, unregistred
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
        self.hass = hass
        self.config = config
        self.windy = WindyPush(hass, config)
        self.pocasi: PocasiPush = PocasiPush(hass, config)
        super().__init__(hass, _LOGGER, name=DOMAIN)

    async def recieved_data(self, webdata):
        """Handle incoming data query."""
        _wslink = self.config_entry.options.get(WSLINK)
        data = webdata.query

        response = None

        if not _wslink and ("ID" not in data or "PASSWORD" not in data):
            _LOGGER.error("Invalid request. No security data provided!")
            raise HTTPUnauthorized

        if _wslink and ("wsid" not in data or "wspw" not in data):
            _LOGGER.error("Invalid request. No security data provided!")
            raise HTTPUnauthorized

        if _wslink:
            id_data = data["wsid"]
            key_data = data["wspw"]
        else:
            id_data = data["ID"]
            key_data = data["PASSWORD"]

        _id = self.config_entry.options.get(API_ID)
        _key = self.config_entry.options.get(API_KEY)

        if id_data != _id or key_data != _key:
            _LOGGER.error("Unauthorised access!")
            raise HTTPUnauthorized

        if self.config_entry.options.get(WINDY_ENABLED):
            response = await self.windy.push_data_to_windy(data)

        if self.config.options.get(POCASI_CZ_ENABLED):
            await self.pocasi.push_data_to_server(data, "WSLINK" if _wslink else "WU")

        remaped_items = (
            remap_wslink_items(data)
            if self.config_entry.options.get(WSLINK)
            else remap_items(data)
        )

        if sensors := check_disabled(self.hass, remaped_items, self.config):
            translate_sensors = [
                await translations(
                    self.hass, DOMAIN, f"sensor.{t_key}", key="name", category="entity"
                )
                for t_key in sensors
                if await translations(
                    self.hass, DOMAIN, f"sensor.{t_key}", key="name", category="entity"
                )
                is not None
            ]
            human_readable = "\n".join(translate_sensors)

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

        response = response or "OK"
        return aiohttp.web.Response(body=f"{response or 'OK'}", status=200)


def register_path(
    hass: HomeAssistant,
    url_path: str,
    coordinator: WeatherDataUpdateCoordinator,
    config: ConfigEntry,
):
    """Register path to handle incoming data."""

    hass_data = hass.data.setdefault(DOMAIN, {})
    debug = config.options.get(DEV_DBG)
    _wslink = config.options.get(WSLINK, False)

    routes: Routes = hass_data.get("routes", Routes())

    if not routes.routes:
        routes = Routes()
        _LOGGER.info("Routes not found, creating new routes")

        if debug:
            _LOGGER.debug("Enabled route is: %s, WSLink is %s", url_path, _wslink)

        try:
            default_route = hass.http.app.router.add_get(
                DEFAULT_URL,
                coordinator.recieved_data if not _wslink else unregistred,
                name="weather_default_url",
            )
            if debug:
                _LOGGER.debug("Default route: %s", default_route)

            wslink_route = hass.http.app.router.add_get(
                WSLINK_URL,
                coordinator.recieved_data if _wslink else unregistred,
                name="weather_wslink_url",
            )
            if debug:
                _LOGGER.debug("WSLink route: %s", wslink_route)

            routes.add_route(
                DEFAULT_URL,
                default_route,
                coordinator.recieved_data if not _wslink else unregistred,
                not _wslink,
            )
            routes.add_route(
                WSLINK_URL, wslink_route, coordinator.recieved_data, _wslink
            )

            hass_data["routes"] = routes

        except RuntimeError as Ex:  # pylint: disable=(broad-except)
            if (
                "Added route will never be executed, method GET is already registered"
                in Ex.args
            ):
                _LOGGER.info("Handler to URL (%s) already registred", url_path)
                return False

            _LOGGER.error("Unable to register URL handler! (%s)", Ex.args)
            return False

        _LOGGER.info(
            "Registered path to handle weather data: %s",
            routes.get_enabled(),  # pylint: disable=used-before-assignment
        )

    if _wslink:
        routes.switch_route(coordinator.recieved_data, WSLINK_URL)
    else:
        routes.switch_route(coordinator.recieved_data, DEFAULT_URL)

    return routes


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the config entry for my device."""

    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    hass_data = hass.data.setdefault(DOMAIN, {})
    hass_data[entry.entry_id] = coordinator

    _wslink = entry.options.get(WSLINK)
    debug = entry.options.get(DEV_DBG)

    if debug:
        _LOGGER.debug("WS Link is %s", "enbled" if _wslink else "disabled")

    route = register_path(
        hass, DEFAULT_URL if not _wslink else WSLINK_URL, coordinator, entry
    )

    if not route:
        _LOGGER.error("Fatal: path not registered!")
        raise PlatformNotReady

    hass_data["route"] = route

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Update setup listener."""

    await hass.config_entries.async_reload(entry.entry_id)

    _LOGGER.info("Settings updated")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    _ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if _ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return _ok
