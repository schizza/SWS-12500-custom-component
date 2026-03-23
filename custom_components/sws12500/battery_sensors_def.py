"""Battery sensors."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)

BATTERY_BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="outside_battery",
        translation_key="outside_battery",
        device_class=BinarySensorDeviceClass.BATTERY,
    ),
    BinarySensorEntityDescription(
        key="indoor_battery",
        translation_key="indoor_battery",
        device_class=BinarySensorDeviceClass.BATTERY,
    ),
    BinarySensorEntityDescription(
        key="ch2_battery",
        translation_key="ch2_battery",
        device_class=BinarySensorDeviceClass.BATTERY,
    ),
)
