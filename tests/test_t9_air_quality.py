"""Tests for the T9 air-quality (HCHO / VOC) sensor support.

Covers what was added for the WSLink ``t9hcho`` / ``t9voclv`` / ``t9bat`` /
``t9cn`` parameters:

- the new constants (``REMAP_WSLINK_ITEMS``, ``CONNECTION_GATED_SENSORS``,
  ``BATTERY_NON_BINARY``, ``VOCLevel`` / ``VOC_LEVEL_MAP``)
- the ``utils.voc_level_to_text`` and ``utils.battery_5step_to_pct`` helpers
- the connection gating in ``utils.remap_wslink_items``
- the new ``SENSOR_TYPES_WSLINK`` entity descriptions
- the ``hcho`` / ``voc`` / ``t9_battery`` entries in the translation files
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.sws12500.const import (
    BATTERY_LIST,
    BATTERY_NON_BINARY,
    CONNECTION_GATED_SENSORS,
    HCHO,
    OUTSIDE_TEMP,
    REMAP_WSLINK_ITEMS,
    T9_BATTERY,
    VOC,
    VOC_LEVEL_MAP,
    VOCLevel,
)
from custom_components.sws12500.sensors_wslink import SENSOR_TYPES_WSLINK
from custom_components.sws12500.utils import battery_5step_to_pct, remap_wslink_items, voc_level_to_text
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import CONCENTRATION_PARTS_PER_BILLION, PERCENTAGE

# Realistic WSLink payload taken from an issue report: the station sends every
# parameter, even for channels with no sensor connected (``*cn == "0"``).
ISSUE_PAYLOAD = {
    "rbar": "1013.3",
    "intem": "25.0",
    "inhum": "44",
    "t1cn": "1",
    "t1tem": "11.3",
    "t1hum": "92",
    "t234c1cn": "1",
    "t234c2cn": "1",
    "t234c3cn": "0",
    "t8cn": "0",
    "t9cn": "1",
    "t9hcho": "57",
    "t9voclv": "5",
    "t9bat": "5",
    "t10cn": "0",
    "t11cn": "0",
    "apiver": "1.00",
}


# --- constants -------------------------------------------------------------


def test_t9_keys_are_remapped() -> None:
    assert REMAP_WSLINK_ITEMS["t9hcho"] == HCHO
    assert REMAP_WSLINK_ITEMS["t9voclv"] == VOC
    assert REMAP_WSLINK_ITEMS["t9bat"] == T9_BATTERY
    # t9cn is intentionally NOT remapped - it is only used as a gating flag.
    assert "t9cn" not in REMAP_WSLINK_ITEMS


def test_connection_gated_sensors_definition() -> None:
    # The T9 HCHO/VOC probe is gated by its own connection flag. (Multi-channel
    # CH2-CH8 probes have their own gates too; we only assert the T9 one here.)
    assert CONNECTION_GATED_SENSORS["t9cn"] == [HCHO, VOC, T9_BATTERY]


def test_t9_battery_is_non_binary_only() -> None:
    assert BATTERY_NON_BINARY == (T9_BATTERY,)
    # the 0-5 / percentage battery must not be treated as a binary low/normal one
    assert T9_BATTERY not in BATTERY_LIST


def test_voc_level_map_is_complete_and_ordered() -> None:
    # 1 == highest VOC reading (worst air) ... 5 == lowest VOC reading (best air)
    assert set(VOC_LEVEL_MAP) == {1, 2, 3, 4, 5}
    assert set(VOC_LEVEL_MAP.values()) == set(VOCLevel)
    assert VOC_LEVEL_MAP[1] is VOCLevel.UNHEALTHY
    assert VOC_LEVEL_MAP[5] is VOCLevel.EXCELLENT
    assert [member.value for member in VOCLevel] == [
        "unhealthy",
        "poor",
        "moderate",
        "good",
        "excellent",
    ]


# --- voc_level_to_text -----------------------------------------------------


@pytest.mark.parametrize("empty", [None, ""])
def test_voc_level_to_text_handles_empty(empty) -> None:
    assert voc_level_to_text(empty) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", VOCLevel.UNHEALTHY),
        ("2", VOCLevel.POOR),
        ("3", VOCLevel.MODERATE),
        ("4", VOCLevel.GOOD),
        ("5", VOCLevel.EXCELLENT),
        (3, VOCLevel.MODERATE),
    ],
)
def test_voc_level_to_text_maps_known_levels(raw, expected) -> None:
    assert voc_level_to_text(raw) == expected


@pytest.mark.parametrize("raw", ["0", "6", 0, 6])
def test_voc_level_to_text_out_of_range_is_none(raw) -> None:
    assert voc_level_to_text(raw) is None


# --- battery_5step_to_pct --------------------------------------------------


@pytest.mark.parametrize("empty", [None, ""])
def test_battery_5step_to_pct_handles_empty(empty) -> None:
    assert battery_5step_to_pct(empty) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0", 0), ("1", 20), ("2", 40), ("3", 60), ("4", 80), ("5", 100), (5, 100)],
)
def test_battery_5step_to_pct_scales_to_percentage(raw, expected) -> None:
    assert battery_5step_to_pct(raw) == expected


# --- remap_wslink_items connection gating ----------------------------------


def test_remap_keeps_t9_group_when_connected() -> None:
    out = remap_wslink_items({"t9cn": "1", "t9hcho": "57", "t9voclv": "5", "t9bat": "5", "t1tem": "11.3"})
    assert out[HCHO] == "57"
    assert out[VOC] == "5"
    assert out[T9_BATTERY] == "5"
    assert out[OUTSIDE_TEMP] == "11.3"


@pytest.mark.parametrize("conn", [{"t9cn": "0"}, {}], ids=["disconnected", "absent"])
def test_remap_drops_t9_group_when_disconnected_or_absent(conn) -> None:
    out = remap_wslink_items({**conn, "t9hcho": "57", "t9voclv": "5", "t9bat": "5", "t1tem": "11.3"})
    assert HCHO not in out
    assert VOC not in out
    assert T9_BATTERY not in out
    # unrelated sensors are untouched by the gating
    assert out[OUTSIDE_TEMP] == "11.3"


def test_remap_issue_payload_exposes_t9_when_connected() -> None:
    out = remap_wslink_items(ISSUE_PAYLOAD)
    # t9cn == "1" -> the T9 sensors are exposed
    assert out[HCHO] == "57"
    assert out[VOC] == "5"
    assert out[T9_BATTERY] == "5"
    # connection flags never leak into the sensor data
    assert "t9cn" not in out
    assert "t9_conn" not in out


# --- sensor entity descriptions -------------------------------------------


@pytest.fixture
def wslink_descriptions():
    return {description.key: description for description in SENSOR_TYPES_WSLINK}


def test_hcho_entity_description(wslink_descriptions) -> None:
    description = wslink_descriptions[HCHO]
    assert description.translation_key == HCHO
    assert description.device_class is SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS
    assert description.native_unit_of_measurement == CONCENTRATION_PARTS_PER_BILLION
    assert description.state_class is SensorStateClass.MEASUREMENT
    # HCHO is a numeric ppb concentration, so value_fn coerces to int.
    assert description.value_fn("57") == 57


def test_voc_entity_description(wslink_descriptions) -> None:
    description = wslink_descriptions[VOC]
    assert description.translation_key == VOC
    assert description.device_class is SensorDeviceClass.ENUM
    assert description.options == list(VOCLevel)
    # ENUM sensors must not declare a state_class
    assert description.state_class is None
    assert description.value_fn("1") == VOCLevel.UNHEALTHY
    assert description.value_fn("5") == "excellent"
    assert description.value_fn(None) is None


def test_t9_battery_entity_description(wslink_descriptions) -> None:
    description = wslink_descriptions[T9_BATTERY]
    assert description.translation_key == T9_BATTERY
    assert description.device_class is SensorDeviceClass.BATTERY
    assert description.native_unit_of_measurement == PERCENTAGE
    assert description.state_class is SensorStateClass.MEASUREMENT
    assert description.suggested_display_precision == 0
    # no explicit icon -> HA renders the battery icon from the device class + %
    assert description.icon is None
    assert description.value_fn("5") == 100
    assert description.value_fn("0") == 0
    assert description.value_fn(None) is None


# --- translation files -----------------------------------------------------

_TRANSLATIONS_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "sws12500" / "translations"


@pytest.mark.parametrize("filename", ["en.json", "cs.json"])
def test_translation_files_have_t9_entries(filename) -> None:
    sensors = json.loads((_TRANSLATIONS_DIR / filename).read_text(encoding="utf-8"))["entity"]["sensor"]

    assert sensors["hcho"]["name"]
    assert sensors["t9_battery"]["name"]

    voc = sensors["voc"]
    assert voc["name"]
    assert set(voc["state"]) == {member.value for member in VOCLevel}
