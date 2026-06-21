"""Sensor platform for SWS12500.

This module creates sensor entities based on the config entry options.

The integration is push-based (webhook), so we avoid reloading the entry for
auto-discovered sensors. Instead, we dynamically add new entities at runtime
using the `async_add_entities` callback stored in `entry.runtime_data`.

Why not reload on auto-discovery?
Reloading a config entry unloads platforms temporarily, which removes coordinator
listeners. With frequent webhook pushes, this can create a window where nothing is
subscribed and the frontend appears "frozen" until another full reload/restart.

Per-entry runtime state lives on `entry.runtime_data` (see data.SWSRuntimeData)
"""

from __future__ import annotations

from functools import cached_property
import logging
from typing import TYPE_CHECKING, Any

from py_typecheck import checked_or

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo, generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import health_sensor
from .const import (
    CHILL_INDEX,
    DEV_DBG,
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
from .data import SWSConfigEntry
from .sensors_common import WeatherSensorEntityDescription
from .sensors_weather import SENSOR_TYPES_WEATHER_API
from .sensors_wslink import SENSOR_TYPES_WSLINK

if TYPE_CHECKING:
    from .coordinator import WeatherDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _auto_enable_derived_sensors(requested: set[str]) -> set[str]:
    """Auto-enable derived sensors when their source fields are present.

    This does NOT model strict dependencies ("if you want X, we force-add inputs").
    Instead, it opportunistically enables derived outputs when the station already
    provides the raw fields needed to compute them.
    """

    expanded = set(requested)

    # Wind azimut depends on wind dir
    if WIND_DIR in expanded:
        expanded.add(WIND_AZIMUT)

    # Heat index depends on temp + humidity
    if OUTSIDE_TEMP in expanded and OUTSIDE_HUMIDITY in expanded:
        expanded.add(HEAT_INDEX)

    # Chill index depends on temp + wind speed
    if OUTSIDE_TEMP in expanded and WIND_SPEED in expanded:
        expanded.add(CHILL_INDEX)

    return expanded


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SWSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Weather Station sensors.

    Stores `async_add_entities` and the sensor-description map on `entry.runtime_data`
    so the webhook handler can add newly discovered entities dynamically without reloading the config entry.
    """

    runtime = config_entry.runtime_data
    coordinator = runtime.coordinator

    # Wire up integration health diagnostic sensor.
    await health_sensor.async_setup_entry(hass, config_entry, async_add_entities)

    wslink_enabled = checked_or(config_entry.options.get(WSLINK), bool, False)
    sensor_types = SENSOR_TYPES_WSLINK if wslink_enabled else SENSOR_TYPES_WEATHER_API

    # Persist platform callback + description map for dynamic entity creation.
    runtime.add_sensor_entities = async_add_entities
    runtime.sensor_descriptions = {desc.key: desc for desc in sensor_types}

    # Connect Ecowitt bridge to sensor platform so it can dynamically add
    # native Ecowitt entities (sensors without internal SWS mapping).
    coordinator.ecowitt_bridge.set_add_entities(async_add_entities)

    sensors_to_load = checked_or(config_entry.options.get(SENSORS_TO_LOAD), list[str], [])
    if not sensors_to_load:
        return

    requested = _auto_enable_derived_sensors(set(sensors_to_load))

    entities: list[WeatherSensor] = [
        WeatherSensor(description, coordinator) for description in sensor_types if description.key in requested
    ]
    async_add_entities(entities)


def add_new_sensors(hass: HomeAssistant, config_entry: SWSConfigEntry, keys: list[str]) -> None:
    """Dynamically add newly discovered sensors without reloading the entry.

    Called by the webhook handler when the station starts sending new fields.

    Design notes:
    - This function is intentionally a safe no-op if the sensor platform hasn't
      finished setting up yet (e.g. callback/description map missing).
    - Unknown payload keys are ignored (only keys with an entity description are added).
    """

    del hass  # kept for backwards-compatible call signature; not used after runtime_data migration

    runtime = config_entry.runtime_data
    add_entities = runtime.add_sensor_entities
    if add_entities is None:
        return

    descriptions = runtime.sensor_descriptions
    coordinator = runtime.coordinator

    new_entities: list[SensorEntity] = [
        WeatherSensor(desc, coordinator) for key in keys if (desc := descriptions.get(key)) is not None
    ]

    if new_entities:
        add_entities(new_entities)


class WeatherSensor(  # pyright: ignore[reportIncompatibleVariableOverride]
    CoordinatorEntity, SensorEntity
):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Implementation of Weather Sensor entity.

    We intentionally keep the coordinator type unparameterized here to avoid
    propagating HA's generic `DataUpdateCoordinator[T]` typing into this module.
    """

    entity_description: WeatherSensorEntityDescription  # pyright: ignore[reportIncompatibleVariableOverride]
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        description: WeatherSensorEntityDescription,
        coordinator: WeatherDataUpdateCoordinator,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = description.key
        self.entity_description = description  # pyright: ignore[reportIncompatibleVariableOverride]  type: ignore[assignment]
        self._dev_log = checked_or(coordinator.config.options.get(DEV_DBG), bool, False)

    @property
    def native_value(self):  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current sensor state.

        Resolution order:
        1) If `value_from_data_fn` is provided, it receives the full payload dict and can compute
           derived values (e.g. battery enum mapping, azimut text, heat/chill indices).
        2) Otherwise we read the raw value for this key from the payload and pass it through `value_fn`.

        Payload normalization:
        - The station sometimes sends empty strings for missing fields; we treat "" as no value (None).
        """
        data: dict[str, Any] = checked_or(self.coordinator.data, dict[str, Any], {})
        key = self.entity_description.key

        if self.entity_description.value_from_data_fn is not None:
            try:
                value = self.entity_description.value_from_data_fn(data)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("native_value compute failed via value_from_data_fn for key=%s", key)
                return None

            return value

        raw = data.get(key)
        if raw is None or raw == "":
            if self._dev_log:
                _LOGGER.debug("native_value missing raw: key=%s raw=%s", key, raw)
            return None

        if self.entity_description.value_fn is None:
            if self._dev_log:
                _LOGGER.debug("native_value has no value_fn: key=%s raw=%s", key, raw)
            return None

        try:
            value = self.entity_description.value_fn(raw)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("native_value compute failed via value_fn for key=%s raw=%s", key, raw)
            return None

        return value

    @property
    def suggested_entity_id(self) -> str:
        """Return name."""
        return generate_entity_id("sensor.{}", self.entity_description.key)

    @cached_property
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
