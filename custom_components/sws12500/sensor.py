"""Sensors definition for SWS12500."""
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfIrradiance,
    UnitOfPrecipitationDepth,
    UnitOfVolumetricFlux,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    DEGREE,
    UV_INDEX,
    PERCENTAGE
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import WeatherDataUpdateCoordinator
from .const import (
    BARO_PRESSURE,
    CH2_HUMIDITY,
    CH2_TEMP,
    DAILY_RAIN,
    DEW_POINT,
    DOMAIN,
    INDOOR_HUMIDITY,
    INDOOR_TEMP,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    RAIN,
    SOLAR_RADIATION,
    UV,
    WIND_DIR,
    WIND_GUST,
    WIND_SPEED,
)


@dataclass
class WeatherSensorEntityDescription(SensorEntityDescription):
    """Describe Weather Sensor entities."""

    attr_fn: Callable[[dict[str, Any]], dict[str, StateType]] = lambda _: {}
    unit_fn: Callable[[bool], str | None] = lambda _: None

SENSOR_TYPES: tuple[WeatherSensorEntityDescription, ...] = (
    WeatherSensorEntityDescription(
        key=INDOOR_TEMP,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        translation_key=INDOOR_TEMP,
    ),
    WeatherSensorEntityDescription(
        key=INDOOR_HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.HUMIDITY,
        translation_key=INDOOR_HUMIDITY,
    ),
    WeatherSensorEntityDescription(
        key=OUTSIDE_TEMP,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        translation_key=OUTSIDE_TEMP,
    ),
    WeatherSensorEntityDescription(
        key=OUTSIDE_HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.HUMIDITY,
        translation_key=OUTSIDE_HUMIDITY,
    ),
    WeatherSensorEntityDescription(
        key=DEW_POINT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        device_class=SensorDeviceClass.TEMPERATURE,
        translation_key=DEW_POINT,
    ),
    WeatherSensorEntityDescription(
        key=BARO_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.INHG,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        suggested_unit_of_measurement=UnitOfPressure.HPA,
        translation_key=BARO_PRESSURE,
    ),
    WeatherSensorEntityDescription(
        key=WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.WIND_SPEED,
        suggested_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:weather-windy",
        translation_key=WIND_SPEED,
    ),
    WeatherSensorEntityDescription(
        key=WIND_GUST,
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.WIND_SPEED,
        suggested_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:windsock",
        translation_key=WIND_GUST,
    ),
    WeatherSensorEntityDescription(
        key=WIND_DIR,
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=None,
        icon="mdi:sign-direction",
        translation_key=WIND_DIR,
    ),
    WeatherSensorEntityDescription(
        key=RAIN,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL,
        suggested_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        suggested_display_precision=2,
        icon="mdi:weather-pouring",
        translation_key=RAIN,
    ),
    WeatherSensorEntityDescription(
        key=DAILY_RAIN,
        native_unit_of_measurement=UnitOfVolumetricFlux.INCHES_PER_DAY,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        suggested_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_DAY,
        suggested_display_precision=2,
        icon="mdi:weather-pouring",
        translation_key=DAILY_RAIN,
    ),
    WeatherSensorEntityDescription(
        key=SOLAR_RADIATION,
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.IRRADIANCE,
        icon="mdi:weather-sunny",
        translation_key=SOLAR_RADIATION,
    ),
    WeatherSensorEntityDescription(
        key=UV,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UV_INDEX,
        icon="mdi:sunglasses",
        translation_key=UV,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
) -> None:
    """Set up Weather Station sensors."""

    coordinator: WeatherDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    sensors = []
    for description in SENSOR_TYPES:
        sensors.append(WeatherSensor(hass, description, coordinator))
    async_add_entities(sensors)


class WeatherSensor(CoordinatorEntity[WeatherDataUpdateCoordinator], SensorEntity):
    """Implementation of Weather Sensor entity."""

    entity_description: WeatherSensorEntityDescription
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        description: WeatherSensorEntityDescription,
        coordinator: WeatherDataUpdateCoordinator,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self.hass = hass
        self.coordinator = coordinator
        self.entity_description = description
        self._state: StateType = None
        self._available = False
        self._attr_unique_id = f"{DOMAIN}.{description.key}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._state = self.coordinator.data.get(self.entity_description.key)

        self.async_write_ha_state()
        self.async_registry_entry_updated()

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self.entity_description.key

    @property
    def native_value(self) -> None:
        """Return value of entity."""
        return self._state

    @property
    def native_unit_of_measurement(self) -> str:
        """Return unit of measurement."""
        return str(self.entity_description.native_unit_of_measurement)

    @property
    def state_class(self) -> str:
        """Return stateClass."""
        return str(self.entity_description.state_class)

    @property
    def device_info(self) -> DeviceInfo:
        """Device info."""
        return DeviceInfo(
            connections=set(),
            name="Weather Station SWS 12500",
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN,)},  # type: ignore[arg-type]
            manufacturer="Schizza",
            model="Weather Station SWS 12500",
        )
