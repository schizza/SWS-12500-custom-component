"""Tests for the binary sensor platform and battery binary sensor entity.

Covers:
- `binary_sensor.async_setup_entry` (with and without battery keys in SENSORS_TO_LOAD)
- `binary_sensor.add_new_binary_sensors` (no-op / dedupe / unknown / new)
- `battery_sensors.BatteryBinarySensor` (`is_on` value mapping + `device_info`)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.sws12500.battery_sensors import BatteryBinarySensor
from custom_components.sws12500.battery_sensors_def import BATTERY_BINARY_SENSORS
from custom_components.sws12500.binary_sensor import add_new_binary_sensors, async_setup_entry
from custom_components.sws12500.const import CH2_BATTERY, DOMAIN, INDOOR_BATTERY, OUTSIDE_BATTERY, SENSORS_TO_LOAD
from custom_components.sws12500.data import SWSRuntimeData


class _CoordinatorStub:
    """Minimal coordinator stub: CoordinatorEntity only stores it, and `is_on` reads `.data`."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data: dict[str, Any] = data if data is not None else {}


def _make_entry(
    *, options: dict[str, Any] | None = None, coordinator: _CoordinatorStub | None = None
) -> tuple[Any, _CoordinatorStub, SWSRuntimeData]:
    """Build a config-entry stub carrying typed runtime_data, like the integration does."""
    coordinator = coordinator or _CoordinatorStub()
    runtime = SWSRuntimeData(
        coordinator=coordinator,  # type: ignore[arg-type]
        health_coordinator=object(),  # type: ignore[arg-type]
        last_options={},
    )
    entry = SimpleNamespace(
        entry_id="test_entry_id",
        options=options if options is not None else {},
        runtime_data=runtime,
    )
    return entry, coordinator, runtime


@pytest.fixture
def hass():
    # binary_sensor platform setup deletes hass; add_new_binary_sensors also deletes it.
    return object()


def _capture_add_entities():
    captured: list[Any] = []

    def _add_entities(entities: list[Any]) -> None:
        captured.extend(entities)

    return captured, _add_entities


def _desc_for(key: str):
    return next(d for d in BATTERY_BINARY_SENSORS if d.key == key)


# --- async_setup_entry -----------------------------------------------------


@pytest.mark.asyncio
async def test_setup_creates_entities_for_battery_keys(hass):
    entry, coordinator, runtime = _make_entry(
        options={SENSORS_TO_LOAD: [OUTSIDE_BATTERY, INDOOR_BATTERY]}
    )
    captured, add_entities = _capture_add_entities()

    await async_setup_entry(hass, entry, add_entities)

    # Callback + description map persisted for dynamic entity creation.
    assert runtime.add_binary_entities is add_entities
    assert set(runtime.binary_descriptions.keys()) == {d.key for d in BATTERY_BINARY_SENSORS}

    # Entities created for the requested battery keys only.
    assert all(isinstance(e, BatteryBinarySensor) for e in captured)
    created_keys = {e.entity_description.key for e in captured}
    assert created_keys == {OUTSIDE_BATTERY, INDOOR_BATTERY}

    # added_binary_keys tracks them.
    assert runtime.added_binary_keys == {OUTSIDE_BATTERY, INDOOR_BATTERY}

    # Entities are bound to our coordinator stub.
    assert all(e.coordinator is coordinator for e in captured)


@pytest.mark.asyncio
async def test_setup_no_battery_keys_adds_nothing(hass):
    entry, _coordinator, runtime = _make_entry(options={SENSORS_TO_LOAD: ["outside_temp"]})
    captured, add_entities = _capture_add_entities()

    await async_setup_entry(hass, entry, add_entities)

    # Callback/descriptions still stored, but no entities created.
    assert runtime.add_binary_entities is add_entities
    assert runtime.binary_descriptions  # populated
    assert captured == []
    assert runtime.added_binary_keys == set()


@pytest.mark.asyncio
async def test_setup_no_sensors_to_load_option_adds_nothing(hass):
    entry, _coordinator, runtime = _make_entry()  # no options at all
    captured, add_entities = _capture_add_entities()

    await async_setup_entry(hass, entry, add_entities)

    assert captured == []
    assert runtime.added_binary_keys == set()


# --- add_new_binary_sensors ------------------------------------------------


def test_add_new_is_noop_when_callback_missing(hass):
    entry, _coordinator, runtime = _make_entry()
    # Platform not set up yet -> no stored callback.
    assert runtime.add_binary_entities is None

    # Must not raise and must not populate anything.
    add_new_binary_sensors(hass, entry, [OUTSIDE_BATTERY])
    assert runtime.added_binary_keys == set()


def test_add_new_ignores_already_added_keys(hass):
    entry, _coordinator, runtime = _make_entry()
    captured, add_entities = _capture_add_entities()
    runtime.add_binary_entities = add_entities
    runtime.binary_descriptions = {d.key: d for d in BATTERY_BINARY_SENSORS}
    runtime.added_binary_keys = {OUTSIDE_BATTERY}

    add_new_binary_sensors(hass, entry, [OUTSIDE_BATTERY])

    # Already added -> no new entities, callback not invoked.
    assert captured == []
    assert runtime.added_binary_keys == {OUTSIDE_BATTERY}


def test_add_new_ignores_unknown_keys(hass):
    entry, _coordinator, runtime = _make_entry()
    captured, add_entities = _capture_add_entities()
    runtime.add_binary_entities = add_entities
    runtime.binary_descriptions = {d.key: d for d in BATTERY_BINARY_SENSORS}

    add_new_binary_sensors(hass, entry, ["totally_unknown_key"])

    assert captured == []
    assert runtime.added_binary_keys == set()


def test_add_new_adds_new_known_keys(hass):
    entry, coordinator, runtime = _make_entry()
    captured, add_entities = _capture_add_entities()
    runtime.add_binary_entities = add_entities
    runtime.binary_descriptions = {d.key: d for d in BATTERY_BINARY_SENSORS}

    # Mix of new known, unknown, and a key we'll mark already-added.
    runtime.added_binary_keys = {INDOOR_BATTERY}
    add_new_binary_sensors(
        hass, entry, [OUTSIDE_BATTERY, CH2_BATTERY, INDOOR_BATTERY, "unknown"]
    )

    created_keys = {e.entity_description.key for e in captured}
    assert created_keys == {OUTSIDE_BATTERY, CH2_BATTERY}
    assert all(isinstance(e, BatteryBinarySensor) for e in captured)
    assert all(e.coordinator is coordinator for e in captured)
    assert runtime.added_binary_keys == {INDOOR_BATTERY, OUTSIDE_BATTERY, CH2_BATTERY}


# --- BatteryBinarySensor ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", True),  # low battery -> on
        (0, True),
        ("1", False),  # battery OK -> off
        (1, False),
        (None, None),  # missing
        ("", None),  # empty string
        ("x", None),  # non-int
        ([], None),  # non-int / TypeError path
    ],
)
def test_is_on_value_mapping(raw, expected):
    coordinator = _CoordinatorStub({OUTSIDE_BATTERY: raw})
    sensor = BatteryBinarySensor(coordinator, _desc_for(OUTSIDE_BATTERY))

    assert sensor.is_on is expected
    assert sensor.unique_id == f"{OUTSIDE_BATTERY}_binary"


def test_is_on_key_absent_returns_none():
    coordinator = _CoordinatorStub({})  # key not present at all
    sensor = BatteryBinarySensor(coordinator, _desc_for(OUTSIDE_BATTERY))

    assert sensor.is_on is None


def test_device_info():
    coordinator = _CoordinatorStub()
    sensor = BatteryBinarySensor(coordinator, _desc_for(OUTSIDE_BATTERY))

    info = sensor.device_info
    assert info["name"] == "Weather Station SWS 12500"
    assert info["manufacturer"] == "Schizza"
    assert info["model"] == "Weather Station SWS 12500"
    assert info["identifiers"] == {(DOMAIN,)}
