"""The Sencor SWS 12500 Weather Station integration."""
import logging

import aiohttp
from aiohttp.web_exceptions import HTTPUnauthorized

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import InvalidStateError, PlatformNotReady
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import API_ID, API_KEY, DEFAULT_URL, DEV_DBG, DOMAIN, WINDY_ENABLED
from .utils import anonymize, check_disabled, remap_items
from .windy_func import WindyPush

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]


class IncorrectDataError(InvalidStateError):
    """Invalid exception."""


class WeatherDataUpdateCoordinator(DataUpdateCoordinator):
    """Manage fetched data."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Init global updater."""
        self.hass = hass
        self.config = config
        self.windy = WindyPush(hass, config)
        super().__init__(hass, _LOGGER, name=DOMAIN)

    async def recieved_data(self, webdata):
        """Handle incoming data query."""
        data = webdata.query
        response = None

        if "ID" not in data or "PASSWORD" not in data:
            _LOGGER.error("Invalid request. No security data provided!")
            raise HTTPUnauthorized

        id_data = data["ID"]
        key_data = data["PASSWORD"]

        _id = self.config_entry.options.get(API_ID)
        _key = self.config_entry.options.get(API_KEY)

        if id_data != _id or key_data != _key:
            _LOGGER.error("Unauthorised access!")
            raise HTTPUnauthorized

        if self.config_entry.options.get(WINDY_ENABLED):
            response = await self.windy.push_data_to_windy(data)

        remaped_items = remap_items(data)

        await check_disabled(self.hass, remaped_items, self.config_entry.options.get(DEV_DBG))

        self.async_set_updated_data(remaped_items)

        if self.config_entry.options.get(DEV_DBG):
            _LOGGER.info("Dev log: %s", anonymize(data))

        response = response if response else "OK"
        return aiohttp.web.Response(body=f"{response}", status=200)


def register_path(
    hass: HomeAssistant, url_path: str, coordinator: WeatherDataUpdateCoordinator
):
    """Register path to handle incoming data."""
    try:
        route = hass.http.app.router.add_route(
            "GET", url_path, coordinator.recieved_data
        )
    except RuntimeError as Ex:  # pylint: disable=(broad-except)
        if "Added route will never be executed, method GET is already registered" in Ex.args:
            _LOGGER.info("Handler to URL (%s) already registred", url_path)
            return True

        _LOGGER.error("Unable to register URL handler! (%s)", Ex.args)
        return False

    _LOGGER.info(
        "Registered path to handle weather data: %s",
        route.get_info(),  # pylint: disable=used-before-assignment
    )
    return True

def unregister_path(hass: HomeAssistant):
    """Unregister path to handle incoming data."""
    _LOGGER.error(
        "Unable to delete webhook from API! Restart HA before adding integration!"
    )


class Weather(WeatherDataUpdateCoordinator):
    """Weather class."""

    def __init__(self, hass: HomeAssistant, config) -> None:
        """Init class."""
        self.hass = hass
        super().__init__(hass, config)

    async def setup_update_listener(self, hass: HomeAssistant, entry: ConfigEntry):
         """Update setup listener."""
         await hass.config_entries.async_reload(entry.entry_id)

         _LOGGER.info("Settings updated")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the config entry for my device."""

    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    hass.data.setdefault(DOMAIN, {})

    hass.data[DOMAIN][entry.entry_id] = coordinator

    weather = Weather(hass, entry)

    if not register_path(hass, DEFAULT_URL, coordinator):
        _LOGGER.error("Fatal: path not registered!")
        raise PlatformNotReady

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(weather.setup_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    _ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if _ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        unregister_path(hass)

    return _ok


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the component.

    This component can only be configured through the Integrations UI.
    """
    hass.data.setdefault(DOMAIN, {})
    return True
