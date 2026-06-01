"""Shared keys for storing integration runtime data.

HA 2025+ pattern: typed `ConfigEntry[SWSRuntimeData]` replaces ad-hoc `hass.data[DOMAIN][entry_id]` dicts.
All per-entry state lives here. Cross-reload shared state (aiohttp route registrations) stays under
hass.data[DOMAIN]["routes"] because it must outlive a single entry reload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.components.binary_sensor import BinarySensorEntityDescription

    from .coordinator import WeatherDataUpdateCoordinator
    from .health_coordinator import HealthCoordinator
    from .sensors_common import WeatherSensorEntityDescription


@dataclass
class SWSRuntimeData:
    """Per-entry runtime state for SWS12500 integration.

    Stored in entry.runtime_data. Type-safe.
    """

    # Core coordinators - required - create during `async_setup_entry`.
    coordinator: WeatherDataUpdateCoordinator
    health_coordinator: HealthCoordinator
    last_options: dict[str, Any]

    # Sensor platform callbacks (set by sensor.async_setup_entry)
    add_sensor_entities: AddEntitiesCallback | None = None
    sensor_descriptions: dict[str, WeatherSensorEntityDescription] = field(default_factory=dict)

    # Binary sensor platform callbacks
    add_binary_entities: AddEntitiesCallback | None = None
    binary_descriptions: dict[str, BinarySensorEntityDescription] = field(default_factory=dict)
    added_binary_keys: set[str] = field(default_factory=set)

    # Health data cache for diagnostics - refreshed by `HealthCoordinator` on each tick.
    health_data: dict[str, Any] | None = None

    # Staleness tracking - in-memory, resets on reload.
    started_at: datetime = field(default_factory=dt_util.utcnow)
    last_seen: dict[str, datetime] = field(default_factory=dict)


# Type alias for typed ConfigEntry
type SWSConfigEntry = ConfigEntry[SWSRuntimeData]
