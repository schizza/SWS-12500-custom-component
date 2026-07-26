"""Every battery key must be classified exactly once.

The station reports batteries in two incompatible ways:

- 0/1 (low/normal)     -> ``BATTERY_LIST``       -> binary sensors
- 0-5 level (5 = full) -> ``BATTERY_NON_BINARY`` -> percentage sensors

Both entity description sets are generated from those tuples, so a key appearing in
both would produce a binary sensor *and* a percentage sensor for the same battery -
and the binary one would collapse levels 1-5 into a single "not low", silently
discarding the reading. A key appearing in neither simply never gets an entity.

The WSLink API has more of both kinds still to implement (`t5lsbat`, `t6c1-7bat` are
0/1; `t8bat`, `t10bat`, `t11bat` are 0-5), so these tests exist to fail the moment a
new `*_BATTERY` constant is added without deciding which kind it is.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import PERCENTAGE

from custom_components.sws12500 import const
from custom_components.sws12500.battery_sensors_def import BATTERY_BINARY_SENSORS, BATTERY_LEVEL_SENSORS
from custom_components.sws12500.const import BATTERY_LIST, BATTERY_NON_BINARY
from custom_components.sws12500.sensors_weather import SENSOR_TYPES_WEATHER_API
from custom_components.sws12500.sensors_wslink import SENSOR_TYPES_WSLINK


def _all_battery_constants() -> set[str]:
    """Every battery key defined in const.py.

    A `*_BATTERY` constant is either a single key (``T9_BATTERY``) or a tuple of them
    for a multi-channel family (``LEAK_CH_BATTERY``); both shapes count, otherwise a
    whole family could be added without the classification tests noticing.
    """
    keys: set[str] = set()
    for name, value in vars(const).items():
        if not name.endswith("_BATTERY"):
            continue
        if isinstance(value, str):
            keys.add(value)
        elif isinstance(value, tuple):
            keys.update(v for v in value if isinstance(v, str))
    return keys


def test_classifications_are_disjoint() -> None:
    """A key in both tuples would get two conflicting entities."""
    overlap = set(BATTERY_LIST) & set(BATTERY_NON_BINARY)
    assert not overlap, f"battery keys classified as both binary and 0-5: {sorted(overlap)}"


def test_every_battery_constant_is_classified() -> None:
    """Adding a `*_BATTERY` constant must force a decision about its kind."""
    classified = set(BATTERY_LIST) | set(BATTERY_NON_BINARY)
    unclassified = _all_battery_constants() - classified

    assert not unclassified, (
        f"unclassified battery keys: {sorted(unclassified)} - add each to BATTERY_LIST "
        "(reported as 0/1) or BATTERY_NON_BINARY (reported as a 0-5 level) in const.py"
    )


def test_classification_covers_only_real_constants() -> None:
    """Neither tuple may list a key that is not an actual battery constant."""
    stray = (set(BATTERY_LIST) | set(BATTERY_NON_BINARY)) - _all_battery_constants()
    assert not stray, f"not `*_BATTERY` constants: {sorted(stray)}"


# ---------------------------------------------------------------------------
# The description sets are generated from the tuples, not hand-maintained
# ---------------------------------------------------------------------------


def test_binary_descriptions_generated_from_battery_list() -> None:
    keys = [desc.key for desc in BATTERY_BINARY_SENSORS]
    assert keys == list(BATTERY_LIST)
    assert all(desc.device_class is BinarySensorDeviceClass.BATTERY for desc in BATTERY_BINARY_SENSORS)


def test_level_descriptions_generated_from_battery_non_binary() -> None:
    keys = [desc.key for desc in BATTERY_LEVEL_SENSORS]
    assert keys == list(BATTERY_NON_BINARY)

    for desc in BATTERY_LEVEL_SENSORS:
        assert desc.device_class is SensorDeviceClass.BATTERY
        assert desc.native_unit_of_measurement == PERCENTAGE
        assert desc.value_fn is not None
        # 5 is full; the raw level must be rendered as a percentage.
        assert desc.value_fn("5") == 100
        assert desc.value_fn("0") == 0


def test_level_batteries_are_not_also_plain_sensors() -> None:
    """A 0-5 battery must not be hand-defined on top of its generated description.

    `BATTERY_LEVEL_SENSORS` is spliced into `SENSOR_TYPES_WSLINK`, so one occurrence
    there is the generated one and is expected; `SENSOR_TYPES_WEATHER_API` does not
    splice them in, so zero is expected there. "At most once" is therefore the
    invariant that holds for both - a second entry is a duplicate entity.

    Complete *absence* of a description is caught by
    `test_level_descriptions_generated_from_battery_non_binary`, which pins the
    generated set to `BATTERY_NON_BINARY` exactly.
    """
    for sensor_types in (SENSOR_TYPES_WSLINK, SENSOR_TYPES_WEATHER_API):
        keys = [desc.key for desc in sensor_types]
        for key in BATTERY_NON_BINARY:
            assert keys.count(key) <= 1, f"{key} defined more than once"


def test_level_batteries_reach_the_sensor_platform() -> None:
    """Every 0-5 battery must actually be spliced into the WSLink platform set.

    The generated tuple existing is not enough - if the `*BATTERY_LEVEL_SENSORS`
    splice were dropped, the classification tests would still pass while the
    percentage entities silently disappeared.
    """
    keys = [desc.key for desc in SENSOR_TYPES_WSLINK]
    for key in BATTERY_NON_BINARY:
        assert key in keys, f"{key} is classified as a 0-5 battery but has no sensor description"


def test_binary_batteries_are_not_plain_sensors_too() -> None:
    """0/1 batteries belong to the binary platform only.

    The legacy plain-sensor variants are deprecated (see `legacy.py`) but still
    present; they must at least not be duplicated.
    """
    for sensor_types in (SENSOR_TYPES_WSLINK, SENSOR_TYPES_WEATHER_API):
        keys = [desc.key for desc in sensor_types]
        for key in BATTERY_LIST:
            assert keys.count(key) <= 1, f"{key} defined more than once"
