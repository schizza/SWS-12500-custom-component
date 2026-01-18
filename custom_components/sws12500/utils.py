"""Utils for SWS12500."""

import logging
import math
from typing import cast

import numpy as np
from py_typecheck import checked
from py_typecheck.core import checked_or

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from .const import (
    AZIMUT,
    DEV_DBG,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    REMAP_ITEMS,
    REMAP_WSLINK_ITEMS,
    SENSORS_TO_LOAD,
    WIND_SPEED,
    UnitOfBat,
    UnitOfDir,
)

_LOGGER = logging.getLogger(__name__)


async def translations(
    hass: HomeAssistant,
    translation_domain: str,
    translation_key: str,
    *,
    key: str = "message",
    category: str = "notify",
) -> str | None:
    """Get translated keys for domain."""

    localize_key = f"component.{translation_domain}.{category}.{translation_key}.{key}"

    language: str = hass.config.language

    _translations = await async_get_translations(
        hass, language, category, [translation_domain]
    )
    if localize_key in _translations:
        return _translations[localize_key]
    return None


async def translated_notification(
    hass: HomeAssistant,
    translation_domain: str,
    translation_key: str,
    translation_placeholders: dict[str, str] | None = None,
    notification_id: str | None = None,
    *,
    key: str = "message",
    category: str = "notify",
):
    """Translate notification."""

    localize_key = f"component.{translation_domain}.{category}.{translation_key}.{key}"

    localize_title = (
        f"component.{translation_domain}.{category}.{translation_key}.title"
    )

    language: str = cast("str", hass.config.language)

    _translations = await async_get_translations(
        hass, language, category, [translation_domain]
    )
    if localize_key in _translations:
        if not translation_placeholders:
            persistent_notification.async_create(
                hass,
                _translations[localize_key],
                _translations[localize_title],
                notification_id,
            )
        else:
            message = _translations[localize_key].format(**translation_placeholders)
            persistent_notification.async_create(
                hass, message, _translations[localize_title], notification_id
            )


async def update_options(
    hass: HomeAssistant,
    entry: ConfigEntry,
    update_key: str,
    update_value: str | list[str] | bool,
) -> bool:
    """Update config.options entry."""
    conf = {**entry.options}
    conf[update_key] = update_value

    return hass.config_entries.async_update_entry(entry, options=conf)


def anonymize(
    data: dict[str, str | int | float | bool],
) -> dict[str, str | int | float | bool]:
    """Anoynimize recieved data."""
    anonym: dict[str, str] = {}
    return {
        anonym[key]: value
        for key, value in data.items()
        if key not in {"ID", "PASSWORD", "wsid", "wspw"}
    }


def remap_items(entities: dict[str, str]) -> dict[str, str]:
    """Remap items in query."""
    return {
        REMAP_ITEMS[key]: value for key, value in entities.items() if key in REMAP_ITEMS
    }


def remap_wslink_items(entities: dict[str, str]) -> dict[str, str]:
    """Remap items in query for WSLink API."""
    return {
        REMAP_WSLINK_ITEMS[key]: value
        for key, value in entities.items()
        if key in REMAP_WSLINK_ITEMS
    }


def loaded_sensors(config_entry: ConfigEntry) -> list[str]:
    """Get loaded sensors."""

    return config_entry.options.get(SENSORS_TO_LOAD) or []


def check_disabled(
    items: dict[str, str], config_entry: ConfigEntry
) -> list[str] | None:
    """Check if we have data for unloaded sensors.

    If so, then add sensor to load queue.

    Returns list of found sensors or None
    """

    log = checked_or(config_entry.options.get(DEV_DBG), bool, False)

    entityFound: bool = False
    _loaded_sensors: list[str] = loaded_sensors(config_entry)
    missing_sensors: list[str] = []

    for item in items:
        if log:
            _LOGGER.info("Checking %s", item)

        if item not in _loaded_sensors:
            missing_sensors.append(item)
            entityFound = True
            if log:
                _LOGGER.info("Add sensor (%s) to loading queue", item)

    return missing_sensors if entityFound else None


def wind_dir_to_text(deg: float) -> UnitOfDir | None:
    """Return wind direction in text representation.

    Returns UnitOfDir or None
    """

    if deg:
        return AZIMUT[int(abs((float(deg) - 11.25) % 360) / 22.5)]

    return None


def battery_level(battery: int) -> UnitOfBat:
    """Return battery level.

    Returns UnitOfBat
    """

    level_map: dict[int, UnitOfBat] = {
        0: UnitOfBat.LOW,
        1: UnitOfBat.NORMAL,
    }

    if (v := checked(battery, int)) is None:
        return UnitOfBat.UNKNOWN

    return level_map.get(v, UnitOfBat.UNKNOWN)


def battery_level_to_icon(battery: UnitOfBat) -> str:
    """Return battery level in icon representation.

    Returns str
    """

    icons = {
        UnitOfBat.LOW: "mdi:battery-low",
        UnitOfBat.NORMAL: "mdi:battery",
    }

    return icons.get(battery, "mdi:battery-unknown")


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (fahrenheit - 32) * 5.0 / 9.0


def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return celsius * 9.0 / 5.0 + 32


def heat_index(
    data: dict[str, int | float | str], convert: bool = False
) -> float | None:
    """Calculate heat index from temperature.

    data: dict with temperature and humidity
    convert: bool, convert recieved data from Celsius to Fahrenheit
    """
    if (temp := checked(data.get(OUTSIDE_TEMP), float)) is None:
        _LOGGER.error("We are missing OUTSIDE TEMP, cannot calculate heat index.")
        return None

    if (rh := checked(data.get(OUTSIDE_HUMIDITY), float)) is None:
        _LOGGER.error("We are missing OUTSIDE HUMIDITY, cannot calculate heat index.")
        return None

    adjustment = None

    if convert:
        temp = celsius_to_fahrenheit(temp)

    simple = 0.5 * (temp + 61.0 + ((temp - 68.0) * 1.2) + (rh * 0.094))
    if ((simple + temp) / 2) > 80:
        full_index = (
            -42.379
            + 2.04901523 * temp
            + 10.14333127 * rh
            - 0.22475541 * temp * rh
            - 0.00683783 * temp * temp
            - 0.05481717 * rh * rh
            + 0.00122874 * temp * temp * rh
            + 0.00085282 * temp * rh * rh
            - 0.00000199 * temp * temp * rh * rh
        )
        if rh < 13 and (temp in np.arange(80, 112, 0.1)):
            adjustment = ((13 - rh) / 4) * math.sqrt((17 - abs(temp - 95)) / 17)

        if rh > 80 and (temp in np.arange(80, 87, 0.1)):
            adjustment = ((rh - 85) / 10) * ((87 - temp) / 5)

        return round((full_index + adjustment if adjustment else full_index), 2)

    return simple


def chill_index(
    data: dict[str, str | float | int], convert: bool = False
) -> float | None:
    """Calculate wind chill index from temperature and wind speed.

    data: dict with temperature and wind speed
    convert: bool, convert recieved data from Celsius to Fahrenheit
    """
    if (temp := checked(data.get(OUTSIDE_TEMP), float)) is None:
        _LOGGER.error("We are missing OUTSIDE TEMP, cannot calculate wind chill index.")
        return None
    if (wind := checked(data.get(WIND_SPEED), float)) is None:
        _LOGGER.error("We are missing WIND SPEED, cannot calculate wind chill index.")
        return None

    if convert:
        temp = celsius_to_fahrenheit(temp)

    return (
        round(
            (
                (35.7 + (0.6215 * temp))
                - (35.75 * (wind**0.16))
                + (0.4275 * (temp * (wind**0.16)))
            ),
            2,
        )
        if temp < 50 and wind > 3
        else temp
    )
