from custom_components.sws12500.sensors_wslink import SENSOR_TYPES_WSLINK
import pytest


def test_sensor_types_wslink_structure():
    assert isinstance(SENSOR_TYPES_WSLINK, tuple)
    assert len(SENSOR_TYPES_WSLINK) > 0
    for sensor in SENSOR_TYPES_WSLINK:
        assert hasattr(sensor, "key")
        assert hasattr(sensor, "native_unit_of_measurement")
