"""Generated entity descriptions for the WSLink binary and battery families.

Everything here is derived from the classification tuples in `const`, so those
tuples stay the single source of truth:

- ``BATTERY_LIST``       -> 0/1 low/normal  -> binary sensors
- ``BATTERY_NON_BINARY`` -> 0-5 level       -> percentage sensors
- ``LEAK_CH``            -> 1/0 leak/dry    -> binary sensors

Generating them from one place is what prevents a key ending up with two
conflicting entities; `tests/test_battery_classification.py` fails if the battery
tuples ever overlap or if a `*_BATTERY` constant is left unclassified.

Which of these are actually loaded is gated in the coordinator by SENSORS_TO_LOAD,
and per-probe by CONNECTION_GATED_SENSORS.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE

from .const import BATTERY_LIST, BATTERY_NON_BINARY, LEAK_CH
from .sensors_common import WeatherSensorEntityDescription, WSBinarySensorEntityDescription
from .utils import battery_5step_to_pct

# The station reports 0 for a low battery, and BinarySensorDeviceClass.BATTERY
# defines `on` as "low" - hence on_value 0.
BATTERY_BINARY_SENSORS: tuple[WSBinarySensorEntityDescription, ...] = tuple(
    WSBinarySensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=BinarySensorDeviceClass.BATTERY,
        on_value=0,
    )
    for key in BATTERY_LIST
)

# The station reports 1 for a leak, and BinarySensorDeviceClass.MOISTURE defines
# `on` as "wet" - hence on_value 1.
LEAK_BINARY_SENSORS: tuple[WSBinarySensorEntityDescription, ...] = tuple(
    WSBinarySensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=BinarySensorDeviceClass.MOISTURE,
        on_value=1,
    )
    for key in LEAK_CH
)

# Every binary family the WSLink platform exposes.
WSLINK_BINARY_SENSORS: tuple[WSBinarySensorEntityDescription, ...] = (
    *BATTERY_BINARY_SENSORS,
    *LEAK_BINARY_SENSORS,
)

BATTERY_LEVEL_SENSORS: tuple[WeatherSensorEntityDescription, ...] = tuple(
    WeatherSensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=battery_5step_to_pct,
    )
    for key in BATTERY_NON_BINARY
)
