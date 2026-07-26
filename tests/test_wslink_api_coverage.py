"""The WSLink API v0.6 must be covered completely and classified correctly.

`API.pdf` (WSLink data upload API, VERSION 0.6) is the contract. This file pins the
parameter list from that document so a future firmware or a refactor cannot quietly
drop a sensor, and - more importantly - so the two battery conventions cannot get
mixed up:

- ``(Normal=1, Low battery=0)``  -> binary sensor
- ``(0~5) remark: 5 is full``    -> percentage sensor

Getting that wrong is silent: a 0-5 battery read as binary reports "not low" for
levels 1-5 and throws four fifths of the reading away.
"""

from __future__ import annotations

import pytest

from custom_components.sws12500.battery_sensors_def import (
    BATTERY_BINARY_SENSORS,
    BATTERY_LEVEL_SENSORS,
    LEAK_BINARY_SENSORS,
)
from custom_components.sws12500.const import (
    BATTERY_LIST,
    BATTERY_NON_BINARY,
    CONNECTION_GATED_SENSORS,
    LEAK_CH,
    LEAK_CH_BATTERY,
    REMAP_WSLINK_ITEMS,
)
from custom_components.sws12500.sensors_wslink import SENSOR_TYPES_WSLINK

# Every upload parameter in API.pdf v0.6, by sensor type.
API_BASE = ["rbar", "abar", "intem", "inhum", "inbat"]
API_TYPE1 = [
    "t1tem", "t1hum", "t1feels", "t1chill", "t1heat", "t1dew", "t1wdir", "t1ws",
    "t1ws10mav", "t1wgust", "t1rainra", "t1rainhr", "t1raindy", "t1rainwy",
    "t1rainmth", "t1rainyr", "t1uvi", "t1solrad", "t1wbgt", "t1bat", "t1cn",
]
API_TYPE234 = [f"t234c{ch}{part}" for ch in range(1, 8) for part in ("tem", "hum", "bat", "cn", "tp")]
API_TYPE5 = [
    "t5lst", "t5lskm", "t5lsf", "t5ls5mtc", "t5ls30mtc", "t5ls1htc", "t5ls1dtc",
    "t5lsbat", "t5lscn",
]
API_TYPE6 = [f"t6c{ch}{part}" for ch in range(1, 8) for part in ("wls", "bat", "cn")]
API_TYPE8 = ["t8pm25", "t8pm10", "t8pm25ai", "t8pm10ai", "t8bat", "t8cn"]
API_TYPE9 = ["t9hcho", "t9voclv", "t9bat", "t9cn"]
API_TYPE10 = ["t10co2", "t10bat", "t10cn"]
API_TYPE11 = ["t11co", "t11bat", "t11cn"]

# Parameters that are not readings: credentials, timestamp, API version, and the
# per-channel probe type (which selects a device class rather than becoming a sensor).
API_NON_READINGS = {"wsid", "wspw", "datetime", "apiver"} | {f"t234c{ch}tp" for ch in range(1, 8)}

ALL_API_PARAMS = [
    *API_BASE, *API_TYPE1, *API_TYPE234, *API_TYPE5,
    *API_TYPE6, *API_TYPE8, *API_TYPE9, *API_TYPE10, *API_TYPE11,
]


def _handled() -> set[str]:
    """Raw parameters the integration does something with."""
    return set(REMAP_WSLINK_ITEMS) | set(CONNECTION_GATED_SENSORS) | API_NON_READINGS


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "params"),
    [
        ("base", API_BASE),
        ("type1", API_TYPE1),
        ("type2/3/4", API_TYPE234),
        ("type5 lightning", API_TYPE5),
        ("type6 water leak", API_TYPE6),
        ("type8 PM", API_TYPE8),
        ("type9 HCHO/VOC", API_TYPE9),
        ("type10 CO2", API_TYPE10),
        ("type11 CO", API_TYPE11),
    ],
)
def test_every_api_parameter_is_handled(name, params) -> None:
    """No upload parameter may be silently ignored."""
    unhandled = sorted(set(params) - _handled())
    assert not unhandled, f"{name}: unhandled WSLink parameters {unhandled}"


def test_no_invented_parameters() -> None:
    """The remap table must not claim parameters the API does not define."""
    unknown = sorted(set(REMAP_WSLINK_ITEMS) - set(ALL_API_PARAMS))
    assert not unknown, f"not in API.pdf v0.6: {unknown}"


def test_gates_are_real_connection_parameters() -> None:
    """Every gate key must be a `*cn` parameter from the document."""
    for gate in CONNECTION_GATED_SENSORS:
        assert gate in ALL_API_PARAMS, f"{gate} is not an API parameter"
        assert gate.endswith("cn"), f"{gate} is not a connection parameter"


def test_every_reading_becomes_an_entity() -> None:
    """A remapped key with no entity would be dead weight in SENSORS_TO_LOAD."""
    sensor_keys = {d.key for d in SENSOR_TYPES_WSLINK}
    binary_keys = {d.key for d in (*BATTERY_BINARY_SENSORS, *LEAK_BINARY_SENSORS)}
    orphans = sorted(set(REMAP_WSLINK_ITEMS.values()) - sensor_keys - binary_keys)
    assert not orphans, f"remapped but never shown: {orphans}"


# ---------------------------------------------------------------------------
# Battery conventions - the part that fails silently when wrong
# ---------------------------------------------------------------------------

# Straight from API.pdf. Batteries documented "(Normal=1, Low battery=0)".
API_BINARY_BATTERIES = ["t1bat", *(f"t234c{ch}bat" for ch in range(1, 8)), "t5lsbat", *(f"t6c{ch}bat" for ch in range(1, 8))]
# Batteries documented "(0~5) remark: 5 is full".
API_LEVEL_BATTERIES = ["t8bat", "t9bat", "t10bat", "t11bat"]


@pytest.mark.parametrize("param", API_BINARY_BATTERIES)
def test_binary_batteries_are_classified_binary(param) -> None:
    key = REMAP_WSLINK_ITEMS[param]
    assert key in BATTERY_LIST, f"{param} is 0/1 in the API but is not a binary battery"
    assert key not in BATTERY_NON_BINARY


@pytest.mark.parametrize("param", API_LEVEL_BATTERIES)
def test_level_batteries_are_classified_as_levels(param) -> None:
    key = REMAP_WSLINK_ITEMS[param]
    assert key in BATTERY_NON_BINARY, f"{param} is 0-5 in the API but is not a level battery"
    assert key not in BATTERY_LIST


def test_every_api_battery_is_accounted_for() -> None:
    """A new battery must land in exactly one of the two tuples."""
    from_api = {REMAP_WSLINK_ITEMS[p] for p in (*API_BINARY_BATTERIES, *API_LEVEL_BATTERIES)}
    classified = set(BATTERY_LIST) | set(BATTERY_NON_BINARY)
    assert from_api <= classified, f"unclassified: {sorted(from_api - classified)}"


def test_level_battery_scale_maps_five_to_full() -> None:
    """0-5 with 5 = full, per the API's own remark."""
    for desc in BATTERY_LEVEL_SENSORS:
        assert desc.value_fn is not None
        assert desc.value_fn("5") == 100
        assert desc.value_fn("0") == 0


# ---------------------------------------------------------------------------
# Water leak
# ---------------------------------------------------------------------------


def test_leak_sensors_cover_all_seven_channels() -> None:
    assert len(LEAK_CH) == 7
    assert len(LEAK_CH_BATTERY) == 7
    assert {d.key for d in LEAK_BINARY_SENSORS} == set(LEAK_CH)


def test_leak_is_on_when_the_station_reports_one() -> None:
    """`Leak=1, No leak=0`, and MOISTURE means `on` = wet - so on_value is 1.

    The batteries in the same family use the opposite convention, which is exactly
    why `on_value` lives in the description.
    """
    for desc in LEAK_BINARY_SENSORS:
        assert desc.on_value == 1
    for desc in BATTERY_BINARY_SENSORS:
        assert desc.on_value == 0


def test_leak_channels_are_gated_by_their_own_connection() -> None:
    for channel in range(1, 8):
        gated = CONNECTION_GATED_SENSORS[f"t6c{channel}cn"]
        assert LEAK_CH[channel - 1] in gated
        assert LEAK_CH_BATTERY[channel - 1] in gated


# ---------------------------------------------------------------------------
# Outdoor probe gating
#
# `t1cn` was in the API but wired to nothing, so a disconnected outdoor probe kept
# publishing its last readings. Gating it is only safe because an *absent* flag no
# longer counts as "disconnected" - otherwise any firmware that omits `t1cn` would
# lose temperature, wind and rain in one go.
# ---------------------------------------------------------------------------


OUTDOOR_PAYLOAD = {"t1tem": "11.3", "t1ws": "4.2", "t1raindy": "0.8", "t1bat": "1"}


def test_disconnected_outdoor_probe_drops_its_readings() -> None:
    from custom_components.sws12500.const import OUTSIDE_TEMP
    from custom_components.sws12500.utils import remap_wslink_items

    out = remap_wslink_items({**OUTDOOR_PAYLOAD, "t1cn": "0"})
    assert OUTSIDE_TEMP not in out
    assert not out, f"nothing from a disconnected probe should survive: {sorted(out)}"


def test_connected_outdoor_probe_keeps_its_readings() -> None:
    from custom_components.sws12500.const import OUTSIDE_TEMP, WIND_SPEED
    from custom_components.sws12500.utils import remap_wslink_items

    out = remap_wslink_items({**OUTDOOR_PAYLOAD, "t1cn": "1"})
    assert out[OUTSIDE_TEMP] == "11.3"
    assert out[WIND_SPEED] == "4.2"


def test_outdoor_readings_survive_a_firmware_that_omits_t1cn() -> None:
    """The regression this gating could have caused, pinned."""
    from custom_components.sws12500.const import OUTSIDE_TEMP, WIND_SPEED
    from custom_components.sws12500.utils import remap_wslink_items

    out = remap_wslink_items(OUTDOOR_PAYLOAD)
    assert out[OUTSIDE_TEMP] == "11.3"
    assert out[WIND_SPEED] == "4.2"


# ---------------------------------------------------------------------------
# Probe type decides the humidity device class
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("channel_type", "expected"),
    [("2", "humidity"), ("3", "humidity"), ("4", "moisture")],
    ids=["thermo-hygrometer", "pool", "soil"],
)
def test_channel_humidity_device_class_follows_the_probe_type(channel_type, expected) -> None:
    """Type 4 is a soil probe, so its `hum` reading is soil moisture, not humidity."""
    from custom_components.sws12500.const import CH2_HUMIDITY
    from custom_components.sws12500.utils import channel_humidity_device_class

    resolved = channel_humidity_device_class({"t234c1tp": channel_type}, CH2_HUMIDITY)
    assert resolved is not None
    assert resolved.value == expected


def test_channel_humidity_device_class_is_none_without_a_type() -> None:
    """No reported type means the description's own device class stands."""
    from custom_components.sws12500.const import CH2_HUMIDITY, OUTSIDE_HUMIDITY
    from custom_components.sws12500.utils import channel_humidity_device_class

    assert channel_humidity_device_class({}, CH2_HUMIDITY) is None
    # Outdoor humidity is not a multi-channel probe at all.
    assert channel_humidity_device_class({"t234c1tp": "4"}, OUTSIDE_HUMIDITY) is None


def test_every_channel_has_its_own_type_parameter() -> None:
    from custom_components.sws12500.const import CH_HUMIDITY_TYPE_PARAM

    assert len(CH_HUMIDITY_TYPE_PARAM) == 7
    assert set(CH_HUMIDITY_TYPE_PARAM.values()) == {f"t234c{ch}tp" for ch in range(1, 8)}


# ---------------------------------------------------------------------------
# `t5lst` sentinel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("raw", "expected"), [("0", 0), ("7", 7), ("120", 120), ("9998", 9998)])
def test_lightning_minutes_passes_real_readings_through(raw, expected) -> None:
    from custom_components.sws12500.utils import lightning_minutes

    assert lightning_minutes(raw) == expected


@pytest.mark.parametrize("raw", ["9999", 9999, "10000", "", None, "n/a"])
def test_lightning_minutes_reports_nothing_for_the_sentinel(raw) -> None:
    """The API documents no unit and its own example uses 9999.

    Reading that as "9999 minutes since the last strike" would show a week-old strike
    on a station that has never seen one.
    """
    from custom_components.sws12500.utils import lightning_minutes

    assert lightning_minutes(raw) is None


def test_lightning_last_description_uses_the_sentinel_helper() -> None:
    from custom_components.sws12500.const import LIGHTNING_LAST
    from custom_components.sws12500.utils import lightning_minutes

    desc = next(d for d in SENSOR_TYPES_WSLINK if d.key == LIGHTNING_LAST)
    assert desc.value_fn is lightning_minutes
    # No device class: TIMESTAMP would need a tz-aware datetime, which the API
    # does not provide.
    assert desc.device_class is None
