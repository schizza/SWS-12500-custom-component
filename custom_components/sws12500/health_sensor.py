"""Health diagnostic sensors for SWS-12500."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any

from py_typecheck import checked, checked_or

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .data import SWSConfigEntry, build_device_info
from .health_coordinator import HealthCoordinator, public_health_snapshot

if TYPE_CHECKING:
    from .health_coordinator import HealthCoordinator


@dataclass(frozen=True, kw_only=True)
class HealthSensorEntityDescription(SensorEntityDescription):
    """Description for health diagnostic sensors."""

    data_path: tuple[str, ...]
    value_fn: Callable[[Any], Any] | None = None


def _resolve_path(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    """Resolve a nested path from a dictionary."""
    current: Any = data
    for key in path:
        if checked(current, dict[str, Any]) is None:
            return None
        current = current.get(key)
    return current


def _on_off(value: Any) -> str:
    """Render a boolean-ish value as `on` / `off`."""
    return "on" if bool(value) else "off"


def _accepted_state(value: Any) -> str:
    """Render ingress acceptance state."""
    return "accepted" if bool(value) else "rejected"


def _authorized_state(value: Any) -> str:
    """Render ingress authorization state."""
    if value is None:
        return "unknown"
    return "authorized" if bool(value) else "unauthorized"


def _timestamp_or_none(value: Any) -> Any:
    """Convert ISO timestamp string to datetime for HA rendering."""
    if not isinstance(value, str):
        return None
    return dt_util.parse_datetime(value)


HEALTH_SENSOR_DESCRIPTIONS: tuple[HealthSensorEntityDescription, ...] = (
    HealthSensorEntityDescription(
        key="integration_health",
        translation_key="integration_health",
        icon="mdi:heart-pulse",
        data_path=("integration_status",),
    ),
    HealthSensorEntityDescription(
        key="active_protocol",
        translation_key="active_protocol",
        icon="mdi:swap-horizontal",
        data_path=("active_protocol",),
    ),
    HealthSensorEntityDescription(
        key="wslink_addon_status",
        translation_key="wslink_addon_status",
        icon="mdi:server-network",
        data_path=("addon", "online"),
        value_fn=lambda value: "online" if value else "offline",
    ),
    HealthSensorEntityDescription(
        key="wslink_addon_name",
        translation_key="wslink_addon_name",
        icon="mdi:package-variant-closed",
        data_path=("addon", "name"),
    ),
    HealthSensorEntityDescription(
        key="wslink_addon_version",
        translation_key="wslink_addon_version",
        icon="mdi:label-outline",
        data_path=("addon", "version"),
    ),
    HealthSensorEntityDescription(
        key="wslink_addon_listen_port",
        translation_key="wslink_addon_listen_port",
        icon="mdi:lan-connect",
        data_path=("addon", "listen_port"),
    ),
    HealthSensorEntityDescription(
        key="wslink_upstream_ha_port",
        translation_key="wslink_upstream_ha_port",
        icon="mdi:transit-connection-variant",
        data_path=("addon", "upstream_ha_port"),
    ),
    HealthSensorEntityDescription(
        key="route_wu_enabled",
        translation_key="route_wu_enabled",
        icon="mdi:transit-connection-horizontal",
        data_path=("routes", "wu_enabled"),
        value_fn=_on_off,
    ),
    HealthSensorEntityDescription(
        key="route_wslink_enabled",
        translation_key="route_wslink_enabled",
        icon="mdi:transit-connection-horizontal",
        data_path=("routes", "wslink_enabled"),
        value_fn=_on_off,
    ),
    HealthSensorEntityDescription(
        key="last_ingress_time",
        translation_key="last_ingress_time",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        data_path=("last_ingress", "time"),
        value_fn=_timestamp_or_none,
    ),
    HealthSensorEntityDescription(
        key="last_ingress_protocol",
        translation_key="last_ingress_protocol",
        icon="mdi:download-network",
        data_path=("last_ingress", "protocol"),
    ),
    HealthSensorEntityDescription(
        key="last_ingress_route_enabled",
        translation_key="last_ingress_route_enabled",
        icon="mdi:check-network",
        data_path=("last_ingress", "route_enabled"),
        value_fn=_on_off,
    ),
    HealthSensorEntityDescription(
        key="last_ingress_accepted",
        translation_key="last_ingress_accepted",
        icon="mdi:check-decagram",
        data_path=("last_ingress", "accepted"),
        value_fn=_accepted_state,
    ),
    HealthSensorEntityDescription(
        key="last_ingress_authorized",
        translation_key="last_ingress_authorized",
        icon="mdi:key",
        data_path=("last_ingress", "authorized"),
        value_fn=_authorized_state,
    ),
    HealthSensorEntityDescription(
        key="last_ingress_reason",
        translation_key="last_ingress_reason",
        icon="mdi:message-alert-outline",
        data_path=("last_ingress", "reason"),
    ),
    HealthSensorEntityDescription(
        key="forward_windy_enabled",
        translation_key="forward_windy_enabled",
        icon="mdi:weather-windy",
        data_path=("forwarding", "windy", "enabled"),
        value_fn=_on_off,
    ),
    HealthSensorEntityDescription(
        key="forward_windy_status",
        translation_key="forward_windy_status",
        icon="mdi:weather-windy",
        data_path=("forwarding", "windy", "last_status"),
    ),
    HealthSensorEntityDescription(
        key="forward_pocasi_enabled",
        translation_key="forward_pocasi_enabled",
        icon="mdi:cloud-upload-outline",
        data_path=("forwarding", "pocasi", "enabled"),
        value_fn=_on_off,
    ),
    HealthSensorEntityDescription(
        key="forward_pocasi_status",
        translation_key="forward_pocasi_status",
        icon="mdi:cloud-upload-outline",
        data_path=("forwarding", "pocasi", "last_status"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SWSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up health diagnostic sensors."""

    del hass  # kept for backwards-compatible call signature; not used after runtime_data migration

    coordinator = entry.runtime_data.health_coordinator

    entities = [
        HealthDiagnosticSensor(coordinator=coordinator, description=description)
        for description in HEALTH_SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class HealthDiagnosticSensor(  # pyright: ignore[reportIncompatibleVariableOverride]
    CoordinatorEntity, SensorEntity
):
    """Health diagnostic sensor for SWS-12500."""

    entity_description: HealthSensorEntityDescription  # pyright: ignore[reportIncompatibleVariableOverride]  type: ignore[assignment]

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: HealthCoordinator,
        description: HealthSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_unique_id = f"{description.key}_health"
        self.entity_description = description  # pyright: ignore[reportIncompatibleVariableOverride]  type: ignore[assignment]

    @property
    def native_value(self) -> Any:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current diagnostic value."""

        data = checked_or(self.coordinator.data, dict[str, Any], {})

        value = _resolve_path(data, self.entity_description.data_path)
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(value)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Expose the health JSON on the main health sensor for debugging.

        Entity attributes are readable by any HA user, so internal network details
        (source IP, internal URLs, raw add-on status) are stripped here; they remain
        available via the authenticated endpoint and the admin-only diagnostics.
        """
        if self.entity_description.key != "integration_health":
            return None

        data = checked_or(self.coordinator.data, dict[str, Any], None)
        if data is None:
            return None

        return public_health_snapshot(data)

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Device info (single shared device for the whole integration)."""
        return build_device_info(self.coordinator.config)
