"""Sensor entities for the SWS12500 integration for old endpoint."""

from typing import cast

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
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

from .const import (
    BARO_PRESSURE,
    CH2_HUMIDITY,
    CH2_TEMP,
    CH3_HUMIDITY,
    CH3_TEMP,
    CH4_HUMIDITY,
    CH4_TEMP,
    CHILL_INDEX,
    DAILY_RAIN,
    DEW_POINT,
    HEAT_INDEX,
    INDOOR_HUMIDITY,
    INDOOR_TEMP,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    RAIN,
    SOLAR_RADIATION,
    UV,
    WIND_AZIMUT,
    WIND_DIR,
    WIND_GUST,
    WIND_SPEED,
    UnitOfDir,
)
from .sensors_common import WeatherSensorEntityDescription
from .utils import wind_dir_to_text

SENSOR_TYPES_WSLINK: tuple[WeatherSensorEntityDescription, ...] = (
    WeatherSensorEntityDescription(
        key=INDOOR_TEMP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        translation_key=INDOOR_TEMP,
        value_fn=lambda data: cast("float", data),
    ),
    WeatherSensorEntityDescription(
        key=INDOOR_HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.HUMIDITY,
        translation_key=INDOOR_HUMIDITY,
        value_fn=lambda data: cast("int", data),
    ),
    WeatherSensorEntityDescription(
        key=OUTSIDE_TEMP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        translation_key=OUTSIDE_TEMP,
        value_fn=lambda data: cast("float", data),
    ),
    WeatherSensorEntityDescription(
        key=OUTSIDE_HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.HUMIDITY,
        translation_key=OUTSIDE_HUMIDITY,
        value_fn=lambda data: cast("int", data),
    ),
    WeatherSensorEntityDescription(
        key=DEW_POINT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        device_class=SensorDeviceClass.TEMPERATURE,
        translation_key=DEW_POINT,
        value_fn=lambda data: cast("float", data),
    ),
    WeatherSensorEntityDescription(
        key=BARO_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        suggested_unit_of_measurement=UnitOfPressure.HPA,
        translation_key=BARO_PRESSURE,
        value_fn=lambda data: cast("float", data),
    ),
    WeatherSensorEntityDescription(
        key=WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.WIND_SPEED,
        suggested_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:weather-windy",
        translation_key=WIND_SPEED,
        value_fn=lambda data: cast("int", data),
    ),
    WeatherSensorEntityDescription(
        key=WIND_GUST,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.WIND_SPEED,
        suggested_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:windsock",
        translation_key=WIND_GUST,
        value_fn=lambda data: cast("float", data),
    ),
    WeatherSensorEntityDescription(
        key=WIND_DIR,
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=None,
        icon="mdi:sign-direction",
        translation_key=WIND_DIR,
        value_fn=lambda data: cast("int", data),
    ),
    WeatherSensorEntityDescription(
        key=WIND_AZIMUT,
        icon="mdi:sign-direction",
        value_fn=lambda data: cast("str", wind_dir_to_text(data)),
        device_class=SensorDeviceClass.ENUM,
        options=list(UnitOfDir),
        translation_key=WIND_AZIMUT,
    ),
    WeatherSensorEntityDescription(
        key=RAIN,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL,
        suggested_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        suggested_display_precision=2,
        icon="mdi:weather-pouring",
        translation_key=RAIN,
        value_fn=lambda data: cast("float", data),
    ),
    WeatherSensorEntityDescription(
        key=DAILY_RAIN,
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        suggested_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_DAY,
        suggested_display_precision=2,
        icon="mdi:weather-pouring",
        translation_key=DAILY_RAIN,
        value_fn=lambda data: cast("float", data),
    ),
    WeatherSensorEntityDescription(
        key=SOLAR_RADIATION,
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.IRRADIANCE,
        icon="mdi:weather-sunny",
        translation_key=SOLAR_RADIATION,
        value_fn=lambda data: cast("float", data),
    ),
    WeatherSensorEntityDescription(
        key=UV,
        name=UV,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UV_INDEX,
        icon="mdi:sunglasses",
        translation_key=UV,
        value_fn=lambda data: cast("float", data),
    ),
    WeatherSensorEntityDescription(
        key=CH2_TEMP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:weather-sunny",
        translation_key=CH2_TEMP,
        value_fn=lambda data: cast("float", data),
    ),
    WeatherSensorEntityDescription(
        key=CH2_HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.HUMIDITY,
        icon="mdi:weather-sunny",
        translation_key=CH2_HUMIDITY,
        value_fn=lambda data: cast("int", data),
    ),
    # WeatherSensorEntityDescription(
    #     key=CH3_TEMP,
    #     native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    #     state_class=SensorStateClass.MEASUREMENT,
    #     device_class=SensorDeviceClass.TEMPERATURE,
    #     suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
    #     icon="mdi:weather-sunny",
    #     translation_key=CH3_TEMP,
    #     value_fn=lambda data: cast(float, data),
    # ),
    # WeatherSensorEntityDescription(
    #     key=CH3_HUMIDITY,
    #     native_unit_of_measurement=PERCENTAGE,
    #     state_class=SensorStateClass.MEASUREMENT,
    #     device_class=SensorDeviceClass.HUMIDITY,
    #     icon="mdi:weather-sunny",
    #     translation_key=CH3_HUMIDITY,
    #     value_fn=lambda data: cast(int, data),
    # ),
    # WeatherSensorEntityDescription(
    #     key=CH4_TEMP,
    #     native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    #     state_class=SensorStateClass.MEASUREMENT,
    #     device_class=SensorDeviceClass.TEMPERATURE,
    #     suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
    #     icon="mdi:weather-sunny",
    #     translation_key=CH4_TEMP,
    #     value_fn=lambda data: cast(float, data),
    # ),
    # WeatherSensorEntityDescription(
    #     key=CH4_HUMIDITY,
    #     native_unit_of_measurement=PERCENTAGE,
    #     state_class=SensorStateClass.MEASUREMENT,
    #     device_class=SensorDeviceClass.HUMIDITY,
    #     icon="mdi:weather-sunny",
    #     translation_key=CH4_HUMIDITY,
    #     value_fn=lambda data: cast(int, data),
    # ),
    WeatherSensorEntityDescription(
        key=HEAT_INDEX,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        icon="mdi:weather-sunny",
        translation_key=HEAT_INDEX,
        value_fn=lambda data: cast("int", data),
    ),
    WeatherSensorEntityDescription(
        key=CHILL_INDEX,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        icon="mdi:weather-sunny",
        translation_key=CHILL_INDEX,
        value_fn=lambda data: cast("int", data),
    ),
)
