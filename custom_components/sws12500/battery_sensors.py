"""Battery binary sensor entities."""

from __future__ import annotations

from typing import Any

from py_typecheck import checked_or

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity


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
        self._attr_unique_id = f"{description.key}_battery"

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
