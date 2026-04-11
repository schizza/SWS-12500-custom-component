"""Battery sensors."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntityDescription

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
    BinarySensorEntityDescription(
        key="ch3_battery",
        translation_key="ch3_battery",
        device_class=BinarySensorDeviceClass.BATTERY,
    ),
    BinarySensorEntityDescription(
        key="ch4_battery",
        translation_key="ch4_battery",
        device_class=BinarySensorDeviceClass.BATTERY,
    ),
    BinarySensorEntityDescription(
        key="ch5_battery",
        translation_key="ch5_battery",
        device_class=BinarySensorDeviceClass.BATTERY,
    ),
    BinarySensorEntityDescription(
        key="ch6_battery",
        translation_key="ch6_battery",
        device_class=BinarySensorDeviceClass.BATTERY,
    ),
    BinarySensorEntityDescription(
        key="ch7_battery",
        translation_key="ch7_battery",
        device_class=BinarySensorDeviceClass.BATTERY,
    ),
    BinarySensorEntityDescription(
        key="ch8_battery",
        translation_key="ch8_battery",
        device_class=BinarySensorDeviceClass.BATTERY,
    ),
)
