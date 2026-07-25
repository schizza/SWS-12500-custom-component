"""Battery sensor templates.

Entity descriptions for both battery kinds are *generated* from the classification
tuples in `const`, so those tuples are the single source of truth:

- ``BATTERY_LIST``       -> 0/1 low/normal  -> binary sensors
- ``BATTERY_NON_BINARY`` -> 0-5 level       -> percentage sensors

Generating both from one place is what prevents the conflict: a key listed in both
tuples would otherwise get a binary sensor (collapsing 0-5 into low/not-low and
throwing away four fifths of the reading) *and* a percentage sensor for the same
battery. `tests/test_battery_classification.py` fails if the tuples ever overlap or
if a `*_BATTERY` constant is left unclassified.

Which of these are actually loaded is gated in the coordinator by SENSORS_TO_LOAD.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntityDescription
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE

from .const import BATTERY_LIST, BATTERY_NON_BINARY
from .sensors_common import WeatherSensorEntityDescription
from .utils import battery_5step_to_pct

BATTERY_BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = tuple(
    BinarySensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=BinarySensorDeviceClass.BATTERY,
    )
    for key in BATTERY_LIST
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
