"""Sensors definition for SWS12500."""
from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any, cast

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UV_INDEX,
    UnitOfIrradiance,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo, generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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
    SENSORS_TO_LOAD,
    SOLAR_RADIATION,
    UV,
    WIND_AZIMUT,
    WIND_DIR,
    WIND_GUST,
    WIND_SPEED,
    UnitOfDir,
)
from .utils import wind_dir_to_text

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class WeatherSensorEntityDescription(SensorEntityDescription):
    """Describe Weather Sensor entities."""

    value_fn: Callable[[Any], int | float | str | None]


SENSOR_TYPES: tuple[WeatherSensorEntityDescription, ...] = (
    WeatherSensorEntityDescription(
        key=INDOOR_TEMP,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        translation_key=INDOOR_TEMP,
        value_fn=lambda data: cast(float, data),
    ),
    WeatherSensorEntityDescription(
        key=INDOOR_HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.HUMIDITY,
        translation_key=INDOOR_HUMIDITY,
        value_fn=lambda data: cast(int, data),
    ),
    WeatherSensorEntityDescription(
        key=OUTSIDE_TEMP,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        translation_key=OUTSIDE_TEMP,
        value_fn=lambda data: cast(float, data),
    ),
    WeatherSensorEntityDescription(
        key=OUTSIDE_HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.HUMIDITY,
        translation_key=OUTSIDE_HUMIDITY,
        value_fn=lambda data: cast(int, data),
    ),
    WeatherSensorEntityDescription(
        key=DEW_POINT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        device_class=SensorDeviceClass.TEMPERATURE,
        translation_key=DEW_POINT,
        value_fn=lambda data: cast(float, data),
    ),
    WeatherSensorEntityDescription(
        key=BARO_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.INHG,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        suggested_unit_of_measurement=UnitOfPressure.HPA,
        translation_key=BARO_PRESSURE,
        value_fn=lambda data: cast(float, data),
    ),
    WeatherSensorEntityDescription(
        key=WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.WIND_SPEED,
        suggested_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:weather-windy",
        translation_key=WIND_SPEED,
        value_fn=lambda data: cast(int, data),
    ),
    WeatherSensorEntityDescription(
        key=WIND_GUST,
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.WIND_SPEED,
        suggested_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:windsock",
        translation_key=WIND_GUST,
        value_fn=lambda data: cast(float, data),
    ),
    WeatherSensorEntityDescription(
        key=WIND_DIR,
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=None,
        icon="mdi:sign-direction",
        translation_key=WIND_DIR,
        value_fn=lambda data: cast(int, data),
    ),
    WeatherSensorEntityDescription(
        key=WIND_AZIMUT,
        icon="mdi:sign-direction",
        value_fn=lambda data: cast(str, wind_dir_to_text(data)),
        device_class=SensorDeviceClass.ENUM,
        options=list(UnitOfDir),
        translation_key=WIND_AZIMUT,
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
        value_fn=lambda data: cast(float, data),
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
        value_fn=lambda data: cast(float, data),
    ),
    WeatherSensorEntityDescription(
        key=SOLAR_RADIATION,
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.IRRADIANCE,
        icon="mdi:weather-sunny",
        translation_key=SOLAR_RADIATION,
        value_fn=lambda data: cast(float, data),
    ),
    WeatherSensorEntityDescription(
        key=UV,
        name=UV,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UV_INDEX,
        icon="mdi:sunglasses",
        translation_key=UV,
        value_fn=lambda data: cast(float, data),
    ),
    WeatherSensorEntityDescription(
        key=CH2_TEMP,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:weather-sunny",
        translation_key=CH2_TEMP,
        value_fn=lambda data: cast(float, data),
    ),
    WeatherSensorEntityDescription(
        key=CH2_HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.HUMIDITY,
        icon="mdi:weather-sunny",
        translation_key=CH2_HUMIDITY,
        value_fn=lambda data: cast(int, data),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Weather Station sensors."""

    coordinator: WeatherDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors_to_load: list = []
    sensors: list = []

    # Check if we have some sensors to load.
    if sensors_to_load := config_entry.options.get(SENSORS_TO_LOAD):
        if WIND_DIR in sensors_to_load:
            sensors_to_load.append(WIND_AZIMUT)
        sensors = [
            WeatherSensor(hass, description, coordinator)
            for description in SENSOR_TYPES
            if description.key in sensors_to_load
        ]
        async_add_entities(sensors)


class WeatherSensor(
    CoordinatorEntity[WeatherDataUpdateCoordinator], RestoreSensor, SensorEntity
):
    """Implementation of Weather Sensor entity."""

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
        self._attr_unique_id = description.key
        self._data = None

    async def async_added_to_hass(self) -> None:
        """Handle listeners to reloaded sensors."""

        await super().async_added_to_hass()

        self.coordinator.async_add_listener(self._handle_coordinator_update)

        # prev_state_data = await self.async_get_last_sensor_data()
        # prev_state = await self.async_get_last_state()
        # if not prev_state:
        #     return
        # self._data = prev_state_data.native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._data = self.coordinator.data.get(self.entity_description.key)

        super()._handle_coordinator_update()

        self.async_write_ha_state()

    @property
    def native_value(self) -> str | int | float | None:
        """Return value of entity."""

        if self.coordinator.data and (WIND_AZIMUT in self.entity_description.key):
            return self.entity_description.value_fn(self.coordinator.data.get(WIND_DIR))

        return self.entity_description.value_fn(self._data)

    @property
    def suggested_entity_id(self) -> str:
        """Return name."""
        return generate_entity_id("sensor.{}", self.entity_description.key)

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
