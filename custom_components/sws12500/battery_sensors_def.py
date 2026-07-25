"""Battery sensors templates.

We create a sensor template here.
Actually loaded sensors are gated in coordinator.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntityDescription

from .const import BATTERY_LIST

BATTERY_BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = tuple(
    BinarySensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=BinarySensorDeviceClass.BATTERY,
    )
    for key in BATTERY_LIST
)
