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
from typing import Any

from aioecowitt import EcoWittListener, EcoWittSensor, EcoWittSensorTypes

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, REMAP_ECOWITT_COMPAT

_LOGGER = logging.getLogger(__name__)

# Reverse mapping: internal key to ecowitt field name
# we need to know which key is internally covered.
_MAPPED_ECOWITT_KEYS: set[str] = set(REMAP_ECOWITT_COMPAT.keys())

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

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
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
        """Store the platform callback for dynamic entity creation."""

        self._add_entities_cb = callback

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

        if self._add_entities_cb is None:
            _LOGGER.debug("Ecowitt sensor %s discovered but platform not ready yet", sensor.key)
            return

        self._know_native_keys.add(sensor.key)
        entity = EcoWittNativeSensor(sensor)
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

    def __init__(self, sensor: EcoWittSensor) -> None:
        """Initialize native EcoWittSensor."""

        self._ecowitt_sensor = sensor
        self._attr_unique_id = f"ecowitt_{sensor.key}"
        self._attr_translation_key = None  # we do not have translation_keys for native sensors
        self._attr_name = sensor.name  # default name, can be overridden by translation_key if we had one

        # set HomeAssistant metadata from aioecowitt sensor type
        ha_meta = STYPE_TO_HA.get(sensor.stype)
        if ha_meta:
            device_class, unit, state_class = ha_meta
            self._attr_device_class = device_class
            self._attr_native_unit_of_measurement = unit
            self._attr_state_class = state_class

            station = sensor.station
            self._attr_device_info = DeviceInfo(
                connections=set(),
                name=f"Ecowitt {station.model}" if station else "Ecowitt station",
                entry_type=DeviceEntryType.SERVICE,
                identifiers={(DOMAIN, f"ecowitt_{station.key}" if station else "ecowitt")},
                manufacturer="Ecowitt impl. from Schizza for SWS12500",
                model=station.model if station else None,
            )

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
