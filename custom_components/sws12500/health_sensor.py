"""Health diagnostic sensor for SWS-12500.

Home Assistant only auto-loads standard platform modules (e.g. `sensor.py`).
This file is a helper module and must be wired from `sensor.py`.
"""

from __future__ import annotations

from functools import cached_property
from typing import Any, cast

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .data import ENTRY_HEALTH_COORD


class HealthSensorEntityDescription(SensorEntityDescription):
    """Description for health diagnostic sensors."""


HEALTH_SENSOR_DESCRIPTIONS: tuple[HealthSensorEntityDescription, ...] = (
    HealthSensorEntityDescription(
        key="Integration status",
        name="Integration status",
        icon="mdi:heart-pulse",
    ),
    HealthSensorEntityDescription(
        key="HomeAssistant source_ip",
        name="Home Assistant source IP",
        icon="mdi:ip",
    ),
    HealthSensorEntityDescription(
        key="HomeAssistant base_url",
        name="Home Assistant base URL",
        icon="mdi:link-variant",
    ),
    HealthSensorEntityDescription(
        key="WSLink Addon response",
        name="WSLink Addon response",
        icon="mdi:server-network",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the health diagnostic sensor."""

    domain_data_any = hass.data.get(DOMAIN)
    if not isinstance(domain_data_any, dict):
        return
    domain_data = cast("dict[str, Any]", domain_data_any)

    entry_data_any = domain_data.get(entry.entry_id)
    if not isinstance(entry_data_any, dict):
        return
    entry_data = cast("dict[str, Any]", entry_data_any)

    coordinator_any = entry_data.get(ENTRY_HEALTH_COORD)
    if coordinator_any is None:
        return

    entities = [
        HealthDiagnosticSensor(
            coordinator=coordinator_any, entry=entry, description=description
        )
        for description in HEALTH_SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)
    # async_add_entities([HealthDiagnosticSensor(coordinator_any, entry)])


class HealthDiagnosticSensor(  # pyright: ignore[reportIncompatibleVariableOverride]
    CoordinatorEntity, SensorEntity
):
    """Health diagnostic sensor for SWS-12500."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: Any,
        entry: ConfigEntry,
        description: HealthSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_unique_id = f"{description.key}_health"
        # self._attr_name = description.name
        # self._attr_icon = "mdi:heart-pulse"

    @property
    def native_value(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return a compact health state."""

        data = cast("dict[str, Any]", getattr(self.coordinator, "data", {}) or {})
        value = data.get("Integration status")
        return cast("str | None", value)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return detailed health diagnostics as attributes."""

        data_any = getattr(self.coordinator, "data", None)
        if not isinstance(data_any, dict):
            return None
        return cast("dict[str, Any]", data_any)

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
