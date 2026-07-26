"""Binary sensor entity for SWS 12500.

One class serves every binary family (battery, water leak). Which raw value means
`on` comes from the description's `on_value`, because the station's convention
differs per family - see `WSBinarySensorEntityDescription`.
"""

from __future__ import annotations

from functools import cached_property
from typing import Any

from py_typecheck import checked_or

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .data import build_device_info
from .sensors_common import WSBinarySensorEntityDescription
from .utils import to_int


class WSBinarySensor(  # pyright: ignore[reportIncompatibleVariableOverride]
    CoordinatorEntity, BinarySensorEntity
):
    """Represent a WSLink binary reading.

    Battery: the station sends ``0`` for low, and ``BinarySensorDeviceClass.BATTERY``
    means ``on`` = low, so ``on_value`` is 0.

    Water leak: the station sends ``1`` for a leak, and
    ``BinarySensorDeviceClass.MOISTURE`` means ``on`` = wet, so ``on_value`` is 1.
    """

    entity_description: WSBinarySensorEntityDescription  # pyright: ignore[reportIncompatibleVariableOverride]

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: Any,
        description: WSBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description  # pyright: ignore[reportIncompatibleVariableOverride]
        self._attr_unique_id = f"{description.key}_binary"

    @property
    def is_on(self) -> bool | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return whether the reading matches this sensor's `on` value."""
        data = checked_or(self.coordinator.data, dict[str, Any], {})
        raw: Any = data.get(self.entity_description.key)

        # `to_int` rather than a bare `int`: the station sometimes sends integer
        # fields as decimals, and a leak reported as "1.0" must still read as wet.
        value = to_int(raw)
        if value is None:
            return None

        return value == self.entity_description.on_value

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Device info (single shared device for the whole integration)."""
        return build_device_info(self.coordinator.config)
