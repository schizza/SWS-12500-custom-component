"""Sensors definition for SWS12500."""

import logging

from homeassistant.components.sensor import RestoreSensor, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo, generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import WeatherDataUpdateCoordinator
from .const import (
    CHILL_INDEX,
    DOMAIN,
    HEAT_INDEX,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    SENSORS_TO_LOAD,
    WIND_AZIMUT,
    WIND_DIR,
    WIND_SPEED,
    WSLINK,
)
from .sensors_common import WeatherSensorEntityDescription
from .sensors_weather import SENSOR_TYPES_WEATHER_API
from .sensors_wslink import SENSOR_TYPES_WSLINK
from .utils import chill_index, heat_index

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Weather Station sensors."""

    coordinator: WeatherDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors_to_load: list = []
    sensors: list = []
    _wslink = config_entry.data.get(WSLINK)

    SENSOR_TYPES = SENSOR_TYPES_WSLINK if _wslink else SENSOR_TYPES_WEATHER_API

    # Check if we have some sensors to load.
    if sensors_to_load := config_entry.options.get(SENSORS_TO_LOAD):
        if WIND_DIR in sensors_to_load:
            sensors_to_load.append(WIND_AZIMUT)
        if (OUTSIDE_HUMIDITY in sensors_to_load) and (OUTSIDE_TEMP in sensors_to_load):
            sensors_to_load.append(HEAT_INDEX)

        if (WIND_SPEED in sensors_to_load) and (OUTSIDE_TEMP in sensors_to_load):
            sensors_to_load.append(CHILL_INDEX)
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

        if self.coordinator.data and (HEAT_INDEX in self.entity_description.key):
            return self.entity_description.value_fn(heat_index(self.coordinator.data))

        if self.coordinator.data and (CHILL_INDEX in self.entity_description.key):
            return self.entity_description.value_fn(chill_index(self.coordinator.data))

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
