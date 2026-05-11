"""Shared keys for storing integration runtime data.

HA 2025+ pattern: structured runtime state stored in entry.runtime_data
instead of loosely-typed hass.data[][] dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core_config import Config
from homeassistant.exceptions import NoEntitySpecifiedError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

if TYPE_CHECKING:
    from . import WeatherDataUpdateCoordinator
    from .ecowitt import EcowittBridge
    from .health_coordinator import HealthCoordinator
    from .sensors_common import WeatherSensorEntityDescription


@dataclass
class SWSRuntimeData:
    """Per-entry runtime state for SWS12500 integration.

    Stored in entry.runtime_data. Type-safe, no string key lookups,
    no checked() boilerplate
    """

    # Core coordinators
    coordinator: WeatherDataUpdateCoordinator
    health_coordinator: HealthCoordinator

    # Sensor platform callbacks (set by sensor.async_setup_entry)
    add_sensor_entities: AddEntitiesCallback | None = None
    sensor_descriptions: dict[str, WeatherSensorEntityDescription] | None = None

    # Binary sensor platform callbacks
    add_binary_entities: AddEntitiesCallback | None = None
    binary_description: dict[str, Any] | None = None
    added_binary_keys: set[str] = field(default_factory=dict)

    # Health data cache for diagnostics
    health_data: dict[str, Any] | None = None


# Type alias for typed ConfigEntry
type SWSConfigEntry = ConfigEntry[SWSRuntimeData]


# Per-entry dict keys stored under hass.data[DOMAIN][entry_id]
ENTRY_COORDINATOR: Final[str] = "coordinator"
ENTRY_ADD_ENTITIES: Final[str] = "async_add_entities"
ENTRY_DESCRIPTIONS: Final[str] = "sensor_descriptions"

# Binary sensor dynamic support
ENTRY_ADD_BINARY_ENTITIES: Final[str] = "async_add_binary_entities"
ENTRY_BINARY_DESCRIPTION: Final[str] = "binary_sensor_description"
ENTRY_ADDED_BINARY_KEYS: Final[str] = "added_binary_keys"

ENTRY_LAST_OPTIONS: Final[str] = "last_options"
ENTRY_HEALTH_COORD: Final[str] = "coord_h"
ENTRY_HEALTH_DATA: Final[str] = "health_data"
