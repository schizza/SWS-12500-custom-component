"""Ecowitt bridge.

Uses the ecowitt library for payload parsing and sensor discovery,
but does NOT start a separate HTTP server. Instead, the HA webhook handler
feeds raw POST data into EcoWittListener.process_data().

Sensors that have an internal mapping (REMAP_ECOWITT_COMPACT) are unified
with the existing SWS sensor pipeline. Unmapped sensors are exposed as
native Ecowitt entities for forward compatibility.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Final

from aioecowitt import EcoWittListener, EcoWittSensor, EcoWittSensorTypes
from aioecowitt.sensor import SENSOR_MAP

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import REMAP_ECOWITT_COMPAT
from .data import SWSConfigEntry, build_device_info

_LOGGER = logging.getLogger(__name__)

# Reverse mapping: internal key to ecowitt field name
# we need to know which key is internally covered.
_MAPPED_ECOWITT_KEYS: set[str] = set(REMAP_ECOWITT_COMPAT.keys())

# Upper bound on auto-created native Ecowitt entities. Bounds entity-registry growth
# from an (authenticated) sender that fabricates many distinct sensor keys.
MAX_NATIVE_ECOWITT_SENSORS: Final = 64


def _build_unit_twins() -> dict[str, frozenset[str]]:
    """Group aioecowitt keys that are unit variants of the same quantity.

    aioecowitt exposes both metric and imperial sensors for many readings (e.g.
    `tempc`/`tempf`, `rainratemm`/`rainratein`), recognisable by a shared display name.
    """
    by_name: dict[str, set[str]] = {}
    for key, meta in SENSOR_MAP.items():
        by_name.setdefault(meta.name, set()).add(key)
    twins: dict[str, frozenset[str]] = {}
    for keys in by_name.values():
        if len(keys) > 1:
            group = frozenset(keys)
            for key in keys:
                twins[key] = group
    return twins


# key -> set of its unit-variant twin keys (incl. itself).
_UNIT_TWINS: dict[str, frozenset[str]] = _build_unit_twins()

# Curated translation keys for the common native (unmapped) Ecowitt sensors. Both unit
# variants map to the same slug so the name is stable regardless of the station's units.
# Long-tail / multi-channel sensors fall back to aioecowitt's English name.
_ECOWITT_TRANSLATIONS: dict[str, str] = {
    "baromabsin": "ecowitt_absolute_pressure",
    "baromabshpa": "ecowitt_absolute_pressure",
    "rainratein": "ecowitt_rain_rate",
    "rainratemm": "ecowitt_rain_rate",
    "eventrainin": "ecowitt_event_rain",
    "eventrainmm": "ecowitt_event_rain",
    "hourlyrainin": "ecowitt_hourly_rain",
    "hourlyrainmm": "ecowitt_hourly_rain",
    "weeklyrainin": "ecowitt_weekly_rain",
    "weeklyrainmm": "ecowitt_weekly_rain",
    "monthlyrainin": "ecowitt_monthly_rain",
    "monthlyrainmm": "ecowitt_monthly_rain",
    "yearlyrainin": "ecowitt_yearly_rain",
    "yearlyrainmm": "ecowitt_yearly_rain",
    "totalrainin": "ecowitt_total_rain",
    "totalrainmm": "ecowitt_total_rain",
    "last24hrainin": "ecowitt_24h_rain",
    "last24hrainmm": "ecowitt_24h_rain",
    "tempfeelsc": "ecowitt_feels_like",
    "tempfeelsf": "ecowitt_feels_like",
    "dewpointinc": "ecowitt_indoor_dewpoint",
    "dewpointinf": "ecowitt_indoor_dewpoint",
    "co2in": "ecowitt_console_co2",
    "co2in_24h": "ecowitt_console_co2_24h",
    "co2": "ecowitt_co2",
    "co2_24h": "ecowitt_co2_24h",
}

# aioecowitt sensor type to HA device class + unit
# We cover most common types, additional will be covered later.
STYPE_TO_HA: dict[EcoWittSensorTypes, tuple[SensorDeviceClass | None, str | None, SensorStateClass | None]] = {
    EcoWittSensorTypes.TEMPERATURE_C: (
        SensorDeviceClass.TEMPERATURE,
        "°C",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.TEMPERATURE_F: (
        SensorDeviceClass.TEMPERATURE,
        "°F",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.HUMIDITY: (
        SensorDeviceClass.HUMIDITY,
        "%",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.PRESSURE_HPA: (
        SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        "hPa",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.PRESSURE_INHG: (
        SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        "inHg",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.SPEED_KPH: (
        SensorDeviceClass.WIND_SPEED,
        "km/h",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.SPEED_MPH: (
        SensorDeviceClass.WIND_SPEED,
        "mph",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.DEGREE: (
        None,
        "°",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.WATT_METERS_SQUARED: (
        SensorDeviceClass.IRRADIANCE,
        "W/m²",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.UV_INDEX: (
        None,
        "UV index",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.PM25: (
        SensorDeviceClass.PM25,
        "µg/m³",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.PM10: (
        SensorDeviceClass.PM10,
        "µg/m³",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.CO2_PPM: (
        SensorDeviceClass.CO2,
        "ppm",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.RAIN_RATE_MM: (
        SensorDeviceClass.PRECIPITATION_INTENSITY,
        "mm/h",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.RAIN_COUNT_MM: (
        SensorDeviceClass.PRECIPITATION,
        "mm",
        SensorStateClass.TOTAL_INCREASING,
    ),
    EcoWittSensorTypes.RAIN_RATE_INCHES: (
        SensorDeviceClass.PRECIPITATION_INTENSITY,
        "in/h",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.RAIN_COUNT_INCHES: (
        SensorDeviceClass.PRECIPITATION,
        "in",
        SensorStateClass.TOTAL_INCREASING,
    ),
    EcoWittSensorTypes.LIGHTNING_COUNT: (
        None,
        "strikes",
        SensorStateClass.TOTAL_INCREASING,
    ),
    EcoWittSensorTypes.LIGHTNING_DISTANCE_KM: (
        SensorDeviceClass.DISTANCE,
        "km",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.SOIL_MOISTURE: (
        SensorDeviceClass.MOISTURE,
        "%",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.BATTERY_VOLTAGE: (
        SensorDeviceClass.VOLTAGE,
        "V",
        SensorStateClass.MEASUREMENT,
    ),
    EcoWittSensorTypes.BATTERY_PERCENTAGE: (
        SensorDeviceClass.BATTERY,
        "%",
        SensorStateClass.MEASUREMENT,
    ),
}


class EcowittBridge:
    """Bridge between HA webhook and aioecowitt parsing.

    We do not run EcoWittListener.start() - this would start separate HTTP server.
    Instead we are calling listener.process_data() manualy from our webhook handler
    and we are just using parsing/discovery logic.
    """

    def __init__(self, hass: HomeAssistant, config: SWSConfigEntry) -> None:
        """Initialize bridge."""

        self.hass = hass
        self.config = config

        # Listener without start - just parser
        self._listener = EcoWittListener()

        # Callback for new sensors
        self._listener.new_sensor_cb.append(self._on_new_sensor)

        # We need to know which native ecowitt sensors have an entity
        self._know_native_keys: set[str] = set()

        # Callback for new entities
        self._add_entities_cb: AddEntitiesCallback | None = None

    def set_add_entities(self, callback: AddEntitiesCallback) -> None:
        """Store the platform callback for dynamic entity creation.

        aioecowitt fires `new_sensor_cb` only once per key. If a payload arrived
        before the platform was ready (callback unset), those unmapped sensors were
        skipped and would never get an entity. Flush them now so nothing is lost.
        """

        self._add_entities_cb = callback

        for sensor in self.unmapped_sensor.values():
            self._on_new_sensor(sensor)

    async def process_payload(self, data: dict[str, Any]) -> dict[str, str]:
        """Process raw Ecowitt POST payload.

        Returns:
            Dict of internal sensor keys -> values (fro mapped senors).
            Unmapped sensors are handeled via _on_new_sensor callback.

        """

        # Let aioecowitt parse payload and derive values,
        # then call new_sensors_cb for new sensors
        self._listener.process_data(data)

        # Get values for internally mapped sensors
        mapped_result: dict[str, str] = {}
        for ecowitt_key, internal_key in REMAP_ECOWITT_COMPAT.items():
            if ecowitt_key in data:
                mapped_result[internal_key] = data[ecowitt_key]

        return mapped_result

    def _on_new_sensor(self, sensor: EcoWittSensor) -> None:
        """Call me by aioecowitt when a new sensor is discovered.

        If the senosor does not have internal mapping,
        create native Ecowitt entity.
        """

        # Sensors with internal mapping handle with current pipeline.
        if sensor.key in _MAPPED_ECOWITT_KEYS:
            _LOGGER.debug(
                "Ecowitt sensor %s has internal mapping, skipping native entity",
                sensor.key,
            )
            return

        # Is entity created?
        if sensor.key in self._know_native_keys:
            return

        # Skip unit-variant duplicates: if a twin (e.g. the °C form of an already
        # mapped °F sensor, or the other unit of an already-created native one) is
        # handled, don't create a second entity. HA converts units via device_class.
        twins = _UNIT_TWINS.get(sensor.key, frozenset())
        if any(twin in _MAPPED_ECOWITT_KEYS or twin in self._know_native_keys for twin in twins):
            _LOGGER.debug("Ecowitt sensor %s skipped: unit-variant twin already handled", sensor.key)
            return

        if self._add_entities_cb is None:
            _LOGGER.debug("Ecowitt sensor %s discovered but platform not ready yet", sensor.key)
            return

        if len(self._know_native_keys) >= MAX_NATIVE_ECOWITT_SENSORS:
            _LOGGER.warning(
                "Reached the cap of %s native Ecowitt sensors; ignoring new key %s",
                MAX_NATIVE_ECOWITT_SENSORS,
                sensor.key,
            )
            return

        self._know_native_keys.add(sensor.key)
        entity = EcoWittNativeSensor(sensor, self.config)
        self._add_entities_cb([entity])

        _LOGGER.info("New native Ecowitt sensor %s (type=%s)", sensor.name, sensor.stype.name)

    @property
    def unmapped_sensor(self) -> dict[str, EcoWittSensor]:
        """Return al sensors that don't have an internal mapping."""

        return {key: sensor for key, sensor in self._listener.sensors.items() if sensor.key not in _MAPPED_ECOWITT_KEYS}

    @property
    def all_sensors(self) -> dict[str, EcoWittSensor]:
        """Return all discovered sensors."""
        return self._listener.sensors


class EcoWittNativeSensor(SensorEntity):
    """Sensor entity for Ecowitt sensors without internal mapping.

    These entities are "pass-through" - their values are directly from EcoWittSensor
    and maps `stype` to HA device class. They do not have coordinator, because
    EcoWittSensor have his own update_cb callback mechanism.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, sensor: EcoWittSensor, config: SWSConfigEntry) -> None:
        """Initialize native EcoWittSensor."""

        self._ecowitt_sensor = sensor
        self._attr_unique_id = f"ecowitt_{sensor.key}"

        # Use a curated translation_key for common native sensors; otherwise fall back
        # to aioecowitt's English name. _attr_translation_key is always set (None when
        # there is no curated translation) so the attribute is well defined.
        self._attr_translation_key = _ECOWITT_TRANSLATIONS.get(sensor.key)
        if self._attr_translation_key is None:
            self._attr_name = sensor.name

        # set HomeAssistant metadata from aioecowitt sensor type.
        # Unknown types still get a usable entity (raw value, no device class/unit).
        ha_meta = STYPE_TO_HA.get(sensor.stype)
        if ha_meta:
            device_class, unit, state_class = ha_meta
            self._attr_device_class = device_class
            self._attr_native_unit_of_measurement = unit
            self._attr_state_class = state_class

        # Share the single integration device (see data.build_device_info); the station
        # type is reflected in the device model rather than a separate Ecowitt device.
        self._attr_device_info = build_device_info(config)

    @property
    def native_value(self) -> StateType | datetime:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Current value from Ecowitt sensor."""
        value = self._ecowitt_sensor.value
        if value is None or value == "":
            return None
        return value

    async def async_added_to_hass(self) -> None:
        """Register update callback when entity is added to HA."""
        self._ecowitt_sensor.update_cb.append(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        """Remove update callback when entity is removed."""
        if self._handle_update in self._ecowitt_sensor.update_cb:
            self._ecowitt_sensor.update_cb.remove(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        """Handle sensor values update from aioecowitt."""
        self.async_write_ha_state()
