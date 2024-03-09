"""Sensors definition for SWS12500."""
from dataclasses import dataclass
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
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import WeatherDataUpdateCoordinator
from .const import (
    BARO_PRESSURE,
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


SENSOR_TYPES: tuple[WeatherSensorEntityDescription, ...] = (
    WeatherSensorEntityDescription(
        key=INDOOR_TEMP,
        name="Indoor temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    WeatherSensorEntityDescription(
        key=INDOOR_HUMIDITY,
        name="Indoor humidity",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.HUMIDITY,
    ),
    WeatherSensorEntityDescription(
        key=OUTSIDE_TEMP,
        name="Outside Temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    WeatherSensorEntityDescription(
        key=OUTSIDE_HUMIDITY,
        name="Outside humidity",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.HUMIDITY,
    ),
    WeatherSensorEntityDescription(
        key=DEW_POINT,
        name="Dew point",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    WeatherSensorEntityDescription(
        key=BARO_PRESSURE,
        name="Barometric pressure",
        native_unit_of_measurement=UnitOfPressure.INHG,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        suggested_unit_of_measurement=UnitOfPressure.HPA,
    ),
    WeatherSensorEntityDescription(
        key=WIND_SPEED,
        name="Wind speed",
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.WIND_SPEED,
        suggested_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:weather-windy",
    ),
    WeatherSensorEntityDescription(
        key=WIND_GUST,
        name="Wind gust",
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.WIND_SPEED,
        suggested_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:windsock",
    ),
    WeatherSensorEntityDescription(
        key=WIND_DIR,
        name="Wind direction",
        native_unit_of_measurement="°",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sign-direction",
    ),
    WeatherSensorEntityDescription(
        key=RAIN,
        name="Rain",
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL,
        suggested_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        suggested_display_precision=2,
        icon="mdi:weather-pouring",
    ),
    WeatherSensorEntityDescription(
        key=DAILY_RAIN,
        name="Daily precipitation",
        native_unit_of_measurement="in/d",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        suggested_unit_of_measurement="mm/h",
        suggested_display_precision=2,
        icon="mdi:weather-pouring",
    ),
    WeatherSensorEntityDescription(
        key=SOLAR_RADIATION,
        name="Solar irradiance",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.IRRADIANCE,
        icon="mdi:weather-sunny",
    ),
    WeatherSensorEntityDescription(
        key=UV,
        name="UV index",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="",
        icon="mdi:sunglasses",
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
        self._attrs: dict[str, Any] = {}
        self._available = False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._state = self.coordinator.data.get(self.entity_description.key)

        self.async_write_ha_state()
        self.async_registry_entry_updated()

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return device class."""
        return self.entity_description.device_class

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return str(self.entity_description.name)

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self.entity_description.key

    @property
    def native_value(self) -> None:
        """Return value of entity."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon of entity."""
        return str(self.entity_description.icon)

    @property
    def native_unit_of_measurement(self) -> str:
        """Return unit of measurement."""
        return str(self.entity_description.native_unit_of_measurement)

    @property
    def state_class(self) -> str:
        """Return stateClass."""

        return str(self.entity_description.state_class)

    @property
    def suggested_unit_of_measurement(self) -> str:
        """Return sugestet_unit_of_measurement."""
        return str(self.entity_description.suggested_unit_of_measurement)

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
