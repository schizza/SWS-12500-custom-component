"""Sensor platform for SWS12500.

This module creates sensor entities based on the config entry options.

The integration is push-based (webhook), so we avoid reloading the entry for
auto-discovered sensors. Instead, we dynamically add new entities at runtime
using the `async_add_entities` callback stored in `hass.data`.

Why not reload on auto-discovery?
Reloading a config entry unloads platforms temporarily, which removes coordinator
listeners. With frequent webhook pushes, this can create a window where nothing is
subscribed and the frontend appears "frozen" until another full reload/restart.

Runtime state is stored under:
    hass.data[DOMAIN][entry_id]  -> dict with known keys (see `data.py`)
"""

from collections.abc import Callable
from functools import cached_property
import logging
from typing import Any, cast

from py_typecheck import checked, checked_or

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo, generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import health_sensor
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
from .data import ENTRY_ADD_ENTITIES, ENTRY_COORDINATOR, ENTRY_DESCRIPTIONS
from .sensors_common import WeatherSensorEntityDescription
from .sensors_weather import SENSOR_TYPES_WEATHER_API
from .sensors_wslink import SENSOR_TYPES_WSLINK

_LOGGER = logging.getLogger(__name__)

# The `async_add_entities` callback accepts a list of Entity-like objects.
# We keep the type loose here to avoid propagating HA generics (`DataUpdateCoordinator[T]`)
# that often end up as "partially unknown" under type-checkers.
_AddEntitiesFn = Callable[[list[SensorEntity]], None]


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
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Weather Station sensors.

    We also store `async_add_entities` and a map of sensor descriptions in `hass.data`
    so the webhook handler can add newly discovered entities dynamically without
    reloading the config entry.
    """

    if (hass_data := checked(hass.data.setdefault(DOMAIN, {}), dict[str, Any])) is None:
        return

    # we have to check if entry_data are present
    # It is created by integration setup, so it should be presnet
    if (entry_data := checked(hass_data.get(config_entry.entry_id), dict[str, Any])) is None:
        # This should not happen in normal operation.
        return

    coordinator = entry_data.get(ENTRY_COORDINATOR)
    if coordinator is None:
        # Coordinator is created by the integration (`__init__.py`). Without it, we cannot set up entities.
        # This should not happen in normal operation; treat it as a no-op setup.
        return

    # Store the platform callback so we can add entities later (auto-discovery) without reload.
    entry_data[ENTRY_ADD_ENTITIES] = async_add_entities

    # Wire up the integration health diagnostic sensor.
    # This is kept in a dedicated module (`health_sensor.py`) for readability.
    await health_sensor.async_setup_entry(hass, config_entry, async_add_entities)

    wslink_enabled = checked_or(config_entry.options.get(WSLINK), bool, False)
    sensor_types = SENSOR_TYPES_WSLINK if wslink_enabled else SENSOR_TYPES_WEATHER_API

    # Keep a descriptions map for dynamic entity creation by key.
    # When the station starts sending a new payload field, the webhook handler can
    # look up its description here and instantiate the matching entity.
    entry_data[ENTRY_DESCRIPTIONS] = {desc.key: desc for desc in sensor_types}

    sensors_to_load = checked_or(config_entry.options.get(SENSORS_TO_LOAD), list[str], [])
    if not sensors_to_load:
        return

    requested = _auto_enable_derived_sensors(set(sensors_to_load))

    entities: list[WeatherSensor] = [
        WeatherSensor(description, coordinator) for description in sensor_types if description.key in requested
    ]
    async_add_entities(entities)

    # Connect Ecowitt bridge to sensor platform,
    # so it can dynamically add native Ecowitt entities
    if hasattr(coordinator, "ecowitt_bridge"):
        coordinator.ecowitt_bridge.set_add_entities(async_add_entities)


def add_new_sensors(hass: HomeAssistant, config_entry: ConfigEntry, keys: list[str]) -> None:
    """Dynamically add newly discovered sensors without reloading the entry.

    Called by the webhook handler when the station starts sending new fields.

    Design notes:
    - This function is intentionally a safe no-op if the sensor platform hasn't
      finished setting up yet (e.g. callback/description map missing).
    - Unknown payload keys are ignored (only keys with an entity description are added).
    """

    if (hass_data := checked(hass.data.get(DOMAIN), dict[str, Any])) is None:
        return

    if (entry_data := checked(hass_data.get(config_entry.entry_id), dict[str, Any])) is None:
        return

    add_entities = entry_data.get(ENTRY_ADD_ENTITIES)
    descriptions = entry_data.get(ENTRY_DESCRIPTIONS)
    coordinator = entry_data.get(ENTRY_COORDINATOR)

    if add_entities is None or descriptions is None or coordinator is None:
        return

    add_entities_fn = cast("_AddEntitiesFn", add_entities)
    descriptions_map = cast("dict[str, WeatherSensorEntityDescription]", descriptions)

    new_entities: list[SensorEntity] = []
    for key in keys:
        desc = descriptions_map.get(key)
        if desc is None:
            continue
        new_entities.append(WeatherSensor(desc, coordinator))

    if new_entities:
        add_entities_fn(new_entities)


class WeatherSensor(  # pyright: ignore[reportIncompatibleVariableOverride]
    CoordinatorEntity, SensorEntity
):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Implementation of Weather Sensor entity.

    We intentionally keep the coordinator type unparameterized here to avoid
    propagating HA's generic `DataUpdateCoordinator[T]` typing into this module.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        description: WeatherSensorEntityDescription,
        coordinator: Any,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)

        self.entity_description = description
        self._attr_unique_id = description.key

        config_entry = getattr(self.coordinator, "config", None)
        self._dev_log = checked_or(
            config_entry.options.get("dev_debug_checkbox") if config_entry is not None else False,
            bool,
            False,
        )

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

        description = cast("WeatherSensorEntityDescription", self.entity_description)

        if description.value_from_data_fn is not None:
            try:
                value = description.value_from_data_fn(data)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("native_value compute failed via value_from_data_fn for key=%s", key)
                return None

            return value

        raw = data.get(key)
        if raw is None or raw == "":
            if self._dev_log:
                _LOGGER.debug("native_value missing raw: key=%s raw=%s", key, raw)
            return None

        if description.value_fn is None:
            if self._dev_log:
                _LOGGER.debug("native_value has no value_fn: key=%s raw=%s", key, raw)
            return None

        try:
            value = description.value_fn(raw)
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
