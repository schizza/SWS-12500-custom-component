"""Utils for SWS12500.

This module contains small helpers used across the integration.

Notable responsibilities:
- Payload remapping: convert raw station/webhook field names into stable internal keys.
- Auto-discovery helpers: detect new payload fields that are not enabled yet and persist them
  to config entry options so sensors can be created dynamically.
- Formatting/conversion helpers (wind direction text, battery mapping, temperature conversions).

Keeping these concerns in one place avoids duplicating logic in the webhook handler and entity code.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Final

from py_typecheck.core import checked_or

from homeassistant.components import persistent_notification
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from .const import (
    AZIMUT,
    CH_HUMIDITY_TYPE_PARAM,
    CH_TYPE_SOIL,
    CHILL_INDEX,
    CONNECTION_GATED_SENSORS,
    DEV_DBG,
    HEAT_INDEX,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    REMAP_ECOWITT_TO_WINDY,
    REMAP_ITEMS,
    REMAP_WSLINK_ITEMS,
    SENSORS_TO_LOAD,
    VOC_LEVEL_MAP,
    WIND_SPEED,
    UnitOfBat,
    UnitOfDir,
    VOCLevel,
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

    _translations = await async_get_translations(hass, language, category, [translation_domain])
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

    localize_title = f"component.{translation_domain}.{category}.{translation_key}.title"

    language: str = hass.config.language

    _translations = await async_get_translations(hass, language, category, [translation_domain])
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
            persistent_notification.async_create(hass, message, _translations[localize_title], notification_id)


async def update_options(hass: HomeAssistant, entry: ConfigEntry, update_key: str, update_value: Any) -> bool:
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
    # `PAS` is Pocasi Meteo's Ecowitt password parameter (not a typo for PASS).
    secrets = {"ID", "PASSWORD", "PAS", "wsid", "wspw", "passkey", "PASSKEY"}

    return {k: ("***" if k in secrets else v) for k, v in data.items()}


def remap_items(entities: dict[str, str]) -> dict[str, str]:
    """Remap legacy (WU-style) payload field names into internal sensor keys.

    The station sends short/legacy field names (e.g. "tempf", "humidity"). Internally we use
    stable keys from `const.py` (e.g. "outside_temp", "outside_humidity"). This function produces
    a normalized dict that the rest of the integration can work with.
    """
    return {REMAP_ITEMS[key]: value for key, value in entities.items() if key in REMAP_ITEMS}


def remap_wslink_items(entities: dict[str, str]) -> dict[str, str]:
    """Remap items in query for WSLink API."""
    items: dict[str, str] = {}
    for item, value in entities.items():
        if item in REMAP_WSLINK_ITEMS:
            items[REMAP_WSLINK_ITEMS[item]] = value

    for conn_key, gated in CONNECTION_GATED_SENSORS.items():
        # Only an explicit "not connected" drops the readings. An absent flag means the
        # firmware does not report one, which is not evidence of a disconnection -
        # treating it as such would wipe out every reading of a probe whose firmware
        # omits the flag, up to and including the main outdoor sensor gated by `t1cn`.
        connection = entities.get(conn_key)
        if connection is not None and str(connection) != "1":
            for key in gated:
                items.pop(key, None)

    return items


def loaded_sensors(config_entry: ConfigEntry) -> list[str]:
    """Return sensor keys currently enabled for this config entry.

    Auto-discovery persists new keys into `config_entry.options[SENSORS_TO_LOAD]`. The sensor
    platform uses this list to decide which entities to create.
    """
    return config_entry.options.get(SENSORS_TO_LOAD) or []


def check_disabled(items: dict[str, str], config_entry: ConfigEntry) -> list[str] | None:
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

    _loaded_sensors: list[str] = loaded_sensors(config_entry)
    missing_sensors: list[str] = []

    for item in items:
        if log:
            _LOGGER.info("Checking %s", item)

        if item not in _loaded_sensors:
            missing_sensors.append(item)
            if log:
                _LOGGER.info("Add sensor (%s) to loading queue", item)

    return missing_sensors or None


def wind_dir_to_text(deg: float | str | None) -> UnitOfDir | None:
    """Return wind direction in text representation.

    Accepts the raw payload value (str), a float, or None. A direction of 0 - or
    a missing/invalid value - is treated as "no reading" (calm) and returns None,
    so a missing wind direction does not render as North.

    Returns UnitOfDir or None
    """

    _deg = to_float(deg)
    if _deg is None or _deg == 0:
        return None

    azimut = AZIMUT[int(abs((_deg - 11.25) % 360) / 22.5)]
    _LOGGER.debug("wind_dir: %s", azimut)
    return azimut


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




def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (fahrenheit - 32) * 5.0 / 9.0


def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return celsius * 9.0 / 5.0 + 32


def to_int(val: Any) -> int | None:
    """Convert int or string (including decimal-formatted, e.g. "180.0") to int."""

    if val is None:
        return None

    if isinstance(val, str) and val.strip() == "":
        return None

    try:
        return int(val)
    except (TypeError, ValueError):
        pass

    # The station sometimes sends integer fields as decimals ("180.0"); accept those.
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def to_float(val: Any) -> float | None:
    """Convert int or string to float."""

    if val is None:
        return None

    if isinstance(val, str) and val.strip() == "":
        return None

    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    else:
        return v


def heat_index(data: dict[str, int | float | str], convert: bool = False) -> float | None:
    """Calculate heat index from temperature.

    data: dict with temperature and humidity
    convert: bool, convert received data from Celsius to Fahrenheit

    The result is floored at the ambient temperature. The NWS step-1 average is only
    meaningful once it reaches 80 F; below that it drifts under the air temperature
    (6.2 C at 40% RH yields 3.9 C), and an entity called "Heat index" reading colder
    than the air is wrong rather than merely imprecise. Always returns Fahrenheit.
    """
    if (temp := to_float(data.get(OUTSIDE_TEMP))) is None:
        _LOGGER.error(
            "We are missing/invalid OUTSIDE TEMP (%s), cannot calculate wind chill index.",
            temp,
        )
        return None

    if (rh := to_float(data.get(OUTSIDE_HUMIDITY))) is None:
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

        return max(round((full_index + adjustment if adjustment else full_index), 2), temp)

    return max(simple, temp)


def chill_index(data: dict[str, str | float | int], convert: bool = False) -> float | None:
    """Calculate wind chill index from temperature and wind speed.

    data: dict with temperature and wind speed
    convert: bool, convert received data from Celsius to Fahrenheit
    """
    temp = to_float(data.get(OUTSIDE_TEMP))
    wind = to_float(data.get(WIND_SPEED))

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
            ((35.7 + (0.6215 * temp)) - (35.75 * (wind**0.16)) + (0.4275 * (temp * (wind**0.16)))),
            2,
        )
        if temp < 50 and wind > 3
        else temp
    )


def voc_level_to_text(value: Any) -> VOCLevel | None:
    """Map the 1-5 VOC level to a text state.

    Goes through `to_int` like every other value_fn: a bare `int()` raises on a garbage
    payload value, which `WeatherSensor.native_value` then logs with a full traceback on
    every push.
    """
    level = to_int(value)
    if level is None:
        return None
    return VOC_LEVEL_MAP.get(level)


def battery_5step_to_pct(value: Any) -> int | None:
    """Convert the 0-5 battery step to a percentage.

    Out-of-range steps are clamped so the reading stays valid for a battery
    device class (see `voc_level_to_text` for why `to_int` is used).
    """
    step = to_int(value)
    if step is None:
        return None

    return round(min(max(step, 0), 5) / 5 * 100)


# The NWS wind-chill formula is defined for mph; WSLink reports wind in m/s.
_MS_TO_MPH: Final = 2.236936


def wslink_heat_index(data: dict[str, Any]) -> float | None:
    """Heat index for a WSLink payload, in Celsius.

    Prefers the station's own `t1heat` reading. Not every WSLink station sends one,
    and without a fallback the entity - which `_auto_enable_derived_sensors` creates
    as soon as temperature and humidity arrive - stays Unavailable forever.

    `heat_index` takes Celsius via `convert=True` but always returns Fahrenheit, so
    the result is converted back to match this entity's native Celsius unit.
    """
    if (reported := to_float(data.get(HEAT_INDEX))) is not None:
        return reported

    # Guard here rather than letting heat_index log an error per push: a payload
    # without these fields is normal, not a fault.
    if to_float(data.get(OUTSIDE_TEMP)) is None or to_float(data.get(OUTSIDE_HUMIDITY)) is None:
        return None

    value_f = heat_index(data, convert=True)
    return None if value_f is None else round(fahrenheit_to_celsius(value_f), 2)


def wslink_chill_index(data: dict[str, Any]) -> float | None:
    """Wind chill for a WSLink payload, in Celsius.

    Prefers the station's own `t1chill` reading; see `wslink_heat_index` for why a
    fallback is needed.

    `chill_index` converts the temperature but *not* the wind speed, and its formula
    expects mph, so the m/s reading is converted here before the Fahrenheit result is
    turned back into Celsius.
    """
    if (reported := to_float(data.get(CHILL_INDEX))) is not None:
        return reported

    temp_c = to_float(data.get(OUTSIDE_TEMP))
    wind_ms = to_float(data.get(WIND_SPEED))
    if temp_c is None or wind_ms is None:
        return None

    value_f = chill_index(
        {
            OUTSIDE_TEMP: celsius_to_fahrenheit(temp_c),
            WIND_SPEED: wind_ms * _MS_TO_MPH,
        }
    )
    return None if value_f is None else round(fahrenheit_to_celsius(value_f), 2)


def remap_ecowitt_to_windy(data: dict[str, Any]) -> dict[str, Any]:
    """Translate an Ecowitt payload into the field names Windy accepts.

    Needed for services that do not speak the Ecowitt protocol - Windy, unlike Pocasi
    Meteo, has no Ecowitt endpoint, so fields such as `baromrelin`, `dewpointf` or
    `tempinf` would simply not be understood.

    Only fields listed in `REMAP_ECOWITT_TO_WINDY` are passed on; see the table there
    for why that is an allowlist rather than a denylist, and where it departs from the
    WU spelling.
    """
    return {out_key: data[eco_key] for eco_key, out_key in REMAP_ECOWITT_TO_WINDY.items() if eco_key in data}


# The WSLink API documents `t5lst` only as "Last Lightning strike time" (integer) and
# its own example uses 9999, which is not a plausible epoch. It is read as minutes
# since the last strike, with 9999 meaning "nothing recorded".
LIGHTNING_NO_STRIKE: Final = 9999


def lightning_minutes(value: Any) -> int | None:
    """Minutes since the last lightning strike, or None when nothing was recorded."""
    minutes = to_int(value)
    if minutes is None or minutes >= LIGHTNING_NO_STRIKE:
        return None
    return minutes


def channel_humidity_device_class(raw_payload: dict[str, Any], key: str) -> SensorDeviceClass | None:
    """Device class for a multi-channel humidity reading, from the probe type.

    WSLink reports what kind of probe sits on each channel via `t234cXtp`. A soil
    probe (type 4) measures soil moisture, not air humidity, so it needs
    `SensorDeviceClass.MOISTURE` rather than `HUMIDITY`.

    Returns None when the channel is not one of the multi-channel ones, or when the
    station did not report a type - the description's own device class then applies.

    This is resolved once, when the entity is created: Home Assistant records the
    device class in the entity registry, and swapping it underneath a live entity
    would rewrite its meaning. Replacing the physical probe therefore needs the
    integration reinstalled, which is the intended trade-off.
    """
    param = CH_HUMIDITY_TYPE_PARAM.get(key)
    if param is None:
        return None

    channel_type = to_int(raw_payload.get(param))
    if channel_type is None:
        return None

    return SensorDeviceClass.MOISTURE if channel_type == CH_TYPE_SOIL else SensorDeviceClass.HUMIDITY
