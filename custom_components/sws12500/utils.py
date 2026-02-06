"""Utils for SWS12500.

This module contains small helpers used across the integration.

Notable responsibilities:
- Payload remapping: convert raw station/webhook field names into stable internal keys.
- Auto-discovery helpers: detect new payload fields that are not enabled yet and persist them
  to config entry options so sensors can be created dynamically.
- Formatting/conversion helpers (wind direction text, battery mapping, temperature conversions).

Keeping these concerns in one place avoids duplicating logic in the webhook handler and entity code.
"""

import logging
import math
from typing import Any, cast

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
    """Anonymize received data for safe logging.

    - Keep all keys, but mask sensitive values.
    - Do not raise on unexpected/missing keys.
    """
    secrets = {"ID", "PASSWORD", "wsid", "wspw"}

    return {k: ("***" if k in secrets else v) for k, v in data.items()}


def remap_items(entities: dict[str, str]) -> dict[str, str]:
    """Remap legacy (WU-style) payload field names into internal sensor keys.

    The station sends short/legacy field names (e.g. "tempf", "humidity"). Internally we use
    stable keys from `const.py` (e.g. "outside_temp", "outside_humidity"). This function produces
    a normalized dict that the rest of the integration can work with.
    """
    return {
        REMAP_ITEMS[key]: value for key, value in entities.items() if key in REMAP_ITEMS
    }


def remap_wslink_items(entities: dict[str, str]) -> dict[str, str]:
    """Remap WSLink payload field names into internal sensor keys.

    WSLink uses a different naming scheme than the legacy endpoint (e.g. "t1tem", "t1ws").
    Just like `remap_items`, this function normalizes the payload to the integration's stable
    internal keys.
    """
    return {
        REMAP_WSLINK_ITEMS[key]: value
        for key, value in entities.items()
        if key in REMAP_WSLINK_ITEMS
    }


def loaded_sensors(config_entry: ConfigEntry) -> list[str]:
    """Return sensor keys currently enabled for this config entry.

    Auto-discovery persists new keys into `config_entry.options[SENSORS_TO_LOAD]`. The sensor
    platform uses this list to decide which entities to create.
    """
    return config_entry.options.get(SENSORS_TO_LOAD) or []


def check_disabled(
    items: dict[str, str], config_entry: ConfigEntry
) -> list[str] | None:
    """Detect payload fields that are not enabled yet (auto-discovery).

    The integration supports "auto-discovery" of sensors: when the station starts sending a new
    field, we can automatically enable and create the corresponding entity.

    This helper compares the normalized payload keys (`items`) with the currently enabled sensor
    keys stored in options (`SENSORS_TO_LOAD`) and returns the missing keys.

    Returns:
        - list[str] of newly discovered sensor keys (to be added/enabled), or
        - None if no new keys were found.

    Notes:
        - Logging is controlled via `DEV_DBG` because payloads can arrive frequently.

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


def battery_level(battery: int | str | None) -> UnitOfBat:
    """Return battery level.

    WSLink payload values often arrive as strings (e.g. "0"/"1"), so we accept
    both ints and strings and coerce to int before mapping.

    Returns UnitOfBat
    """

    level_map: dict[int, UnitOfBat] = {
        0: UnitOfBat.LOW,
        1: UnitOfBat.NORMAL,
    }

    if (battery is None) or (battery == ""):
        return UnitOfBat.UNKNOWN

    vi: int
    if isinstance(battery, int):
        vi = battery
    else:
        try:
            vi = int(battery)
        except ValueError:
            return UnitOfBat.UNKNOWN

    return level_map.get(vi, UnitOfBat.UNKNOWN)


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


def _to_float(val: Any) -> float | None:
    """Convert int or string to float."""

    if not val:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    else:
        return v


def heat_index(
    data: dict[str, int | float | str], convert: bool = False
) -> float | None:
    """Calculate heat index from temperature.

    data: dict with temperature and humidity
    convert: bool, convert recieved data from Celsius to Fahrenheit
    """
    if (temp := _to_float(data.get(OUTSIDE_TEMP))) is None:
        _LOGGER.error(
            "We are missing/invalid OUTSIDE TEMP (%s), cannot calculate wind chill index.",
            temp,
        )
        return None

    if (rh := _to_float(data.get(OUTSIDE_HUMIDITY))) is None:
        _LOGGER.error(
            "We are missing/invalid OUTSIDE HUMIDITY (%s), cannot calculate wind chill index.",
            rh,
        )
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
        if rh < 13 and (80 <= temp <= 112):
            adjustment = ((13 - rh) / 4) * math.sqrt((17 - abs(temp - 95)) / 17)

        if rh > 80 and (80 <= temp <= 87):
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
    temp = _to_float(data.get(OUTSIDE_TEMP))
    wind = _to_float(data.get(WIND_SPEED))

    if temp is None:
        _LOGGER.error(
            "We are missing/invalid OUTSIDE TEMP (%s), cannot calculate wind chill index.",
            temp,
        )
        return None

    if wind is None:
        _LOGGER.error(
            "We are missing/invalid WIND SPEED (%s), cannot calculate wind chill index.",
            wind,
        )
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
