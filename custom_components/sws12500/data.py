"""Shared keys for storing integration runtime data.

HA 2025+ pattern: typed `ConfigEntry[SWSRuntimeData]` replaces ad-hoc `hass.data[DOMAIN][entry_id]` dicts.
All per-entry state lives here. Cross-reload shared state (aiohttp route registrations) stays under
hass.data[DOMAIN]["routes"] because it must outlive a single entry reload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from py_typecheck import checked_or

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .conflicts import effective_protocols
from .const import DOMAIN, WSLINK

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

    # Ecowitt station model (e.g. "GW1000"), learned from the first Ecowitt payload.
    ecowitt_model: str | None = None


# Type alias for typed ConfigEntry
type SWSConfigEntry = ConfigEntry[SWSRuntimeData]


def _station_model(entry: SWSConfigEntry) -> str:
    """Return the device model label reflecting the running station type.

    Ecowitt (with the learned model when available), else WSLink, else PWS.

    Uses the *effective* protocols so a stale both-enabled config reports the endpoint
    that is actually wired up, rather than one that is being ignored.
    """
    legacy, ecowitt = effective_protocols(entry)

    if ecowitt:
        runtime = getattr(entry, "runtime_data", None)
        model = getattr(runtime, "ecowitt_model", None) if runtime is not None else None
        return f"Ecowitt {model}" if model else "Ecowitt"
    if legacy and checked_or(entry.options.get(WSLINK), bool, False):
        return "WSLink"
    return "PWS"


def build_device_info(entry: SWSConfigEntry) -> DeviceInfo:
    """Single device shared by all entities (SWS, battery, health, native Ecowitt).

    Keeps the existing ``{(DOMAIN,)}`` identifier so no device-registry migration is
    needed; the model reflects the active station type.
    """
    return DeviceInfo(
        identifiers={(DOMAIN,)},  # type: ignore[arg-type]
        name="Weather Station SWS 12500",
        entry_type=DeviceEntryType.SERVICE,
        manufacturer="Schizza",
        model=_station_model(entry),
    )
