"""Utils for SWS12500."""

import logging
import math
from typing import Any

import numpy as np

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
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
) -> str:
    """Get translated keys for domain."""

    localize_key = f"component.{translation_domain}.{category}.{translation_key}.{key}"

    language = hass.config.language

    _translations = await async_get_translations(
        hass, language, category, [translation_domain]
    )
    if localize_key in _translations:
        return _translations[localize_key]


async def translated_notification(
    hass: HomeAssistant,
    translation_domain: str,
    translation_key: str,
    translation_placeholders: dict[str, str] | None = None,
    notification_id: str | None = None,
    *,
    key: str = "message",
    category: str = "notify",
) -> str:
    """Translate notification."""

    localize_key = f"component.{translation_domain}.{category}.{translation_key}.{key}"

    localize_title = (
        f"component.{translation_domain}.{category}.{translation_key}.title"
    )

    language = hass.config.language

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
    hass: HomeAssistant, entry: ConfigEntry, update_key, update_value
) -> None:
    """Update config.options entry."""
    conf = {**entry.options}
    conf[update_key] = update_value

    return hass.config_entries.async_update_entry(entry, options=conf)


def anonymize(data):
    """Anoynimize recieved data."""

    anonym = {}
    for k in data:
        if k not in ("ID", "PASSWORD", "wsid", "wspw"):
            anonym[k] = data[k]

    return anonym


def remap_items(entities):
    """Remap items in query."""
    items = {}
    for item in entities:
        if item in REMAP_ITEMS:
            items[REMAP_ITEMS[item]] = entities[item]

    return items


def remap_wslink_items(entities):
    """Remap items in query for WSLink API."""
    items = {}
    for item in entities:
        if item in REMAP_WSLINK_ITEMS:
            items[REMAP_WSLINK_ITEMS[item]] = entities[item]

    return items


def loaded_sensors(config_entry: ConfigEntry) -> list | None:
    """Get loaded sensors."""

    return (
        config_entry.options.get(SENSORS_TO_LOAD)
        if config_entry.options.get(SENSORS_TO_LOAD)
        else []
    )


def check_disabled(
    hass: HomeAssistant, items, config_entry: ConfigEntry
) -> list | None:
    """Check if we have data for unloaded sensors.

    If so, then add sensor to load queue.

    Returns list of found sensors or None
    """

    log: bool = config_entry.options.get(DEV_DBG)
    entityFound: bool = False
    _loaded_sensors = loaded_sensors(config_entry)
    missing_sensors: list = []

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


def heat_index(data: Any) -> UnitOfTemperature:
    """Calculate heat index from temperature."""

    temp = float(data[OUTSIDE_TEMP])
    rh = float(data[OUTSIDE_HUMIDITY])
    adjustment = None

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


def chill_index(data: Any) -> UnitOfTemperature:
    """Calculate wind chill index."""

    temp = float(data[OUTSIDE_TEMP])
    wind = float(data[WIND_SPEED])

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
