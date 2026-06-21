"""Battery binary sensor entities for SWS 12500.

Expose low-batter warnings as binary sensors.
"""

from __future__ import annotations

from functools import cached_property
from typing import Any

from py_typecheck import checked_or

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .data import build_device_info


class BatteryBinarySensor(  # pyright: ignore[reportIncompatibleVariableOverride]
    CoordinatorEntity, BinarySensorEntity
):
    """Represent a low-battery binary sensor.

    Station payload uses:
    - ``0`` => low battery (binary sensor is ``on``)
    - ``1`` => battery OK (binary sensor is ``off``)
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: Any,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the battery binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{description.key}_binary"

    @property
    def is_on(self) -> bool | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return low-battery state.

        ``True`` means low battery for ``BinarySensorDeviceClass.BATTERY``.
        """
        data = checked_or(self.coordinator.data, dict[str, Any], {})
        raw: Any = data.get(self.entity_description.key)

        if raw is None or raw == "":
            return None

        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None

        return value == 0

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Device info (single shared device for the whole integration)."""
        return build_device_info(self.coordinator.config)
