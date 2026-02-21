from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.sws12500.const import (
    CHILL_INDEX,
    HEAT_INDEX,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    SENSORS_TO_LOAD,
    WIND_AZIMUT,
    WIND_DIR,
    WIND_SPEED,
    WSLINK,
)
from custom_components.sws12500.data import (
    ENTRY_ADD_ENTITIES,
    ENTRY_COORDINATOR,
    ENTRY_DESCRIPTIONS,
)
from custom_components.sws12500.sensor import (
    WeatherSensor,
    _auto_enable_derived_sensors,
    add_new_sensors,
    async_setup_entry,
)
from custom_components.sws12500.sensors_weather import SENSOR_TYPES_WEATHER_API
from custom_components.sws12500.sensors_wslink import SENSOR_TYPES_WSLINK


@dataclass(slots=True)
class _ConfigEntryStub:
    entry_id: str
    options: dict[str, Any]


class _CoordinatorStub:
    """Minimal coordinator stub for WeatherSensor and platform setup."""

    def __init__(
        self, data: dict[str, Any] | None = None, *, config: Any | None = None
    ) -> None:
        self.data = data if data is not None else {}
        self.config = config


@pytest.fixture
def hass():
    # Use a very small hass-like object; sensor platform uses only `hass.data`.
    class _Hass:
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}

    return _Hass()


@pytest.fixture
def config_entry() -> _ConfigEntryStub:
    return _ConfigEntryStub(entry_id="test_entry_id", options={})


def _capture_add_entities():
    captured: list[Any] = []

    def _add_entities(entities: list[Any]) -> None:
        captured.extend(entities)

    return captured, _add_entities


def test_auto_enable_derived_sensors_wind_azimut():
    requested = {WIND_DIR}
    expanded = _auto_enable_derived_sensors(requested)
    assert WIND_DIR in expanded
    assert WIND_AZIMUT in expanded


def test_auto_enable_derived_sensors_heat_index():
    requested = {OUTSIDE_TEMP, OUTSIDE_HUMIDITY}
    expanded = _auto_enable_derived_sensors(requested)
    assert HEAT_INDEX in expanded


def test_auto_enable_derived_sensors_chill_index():
    requested = {OUTSIDE_TEMP, WIND_SPEED}
    expanded = _auto_enable_derived_sensors(requested)
    assert CHILL_INDEX in expanded


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_no_coordinator_is_noop(hass, config_entry):
    # No entry dict created by integration yet; async_setup_entry should be defensive and no-op.
    captured, add_entities = _capture_add_entities()

    await async_setup_entry(hass, config_entry, add_entities)

    assert captured == []


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_stores_callback_and_descriptions_even_if_no_sensors_to_load(
    hass, config_entry
):
    # Prepare runtime entry data and coordinator like integration does.
    hass.data.setdefault("sws12500", {})
    hass.data["sws12500"][config_entry.entry_id] = {
        ENTRY_COORDINATOR: _CoordinatorStub()
    }

    captured, add_entities = _capture_add_entities()

    # No SENSORS_TO_LOAD set -> early return, but it should still store callback + descriptions.
    await async_setup_entry(hass, config_entry, add_entities)

    entry_data = hass.data["sws12500"][config_entry.entry_id]
    assert entry_data[ENTRY_ADD_ENTITIES] is add_entities
    assert isinstance(entry_data[ENTRY_DESCRIPTIONS], dict)
    assert captured == []


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_selects_weather_api_descriptions_when_wslink_disabled(
    hass, config_entry
):
    hass.data.setdefault("sws12500", {})
    hass.data["sws12500"][config_entry.entry_id] = {
        ENTRY_COORDINATOR: _CoordinatorStub()
    }

    captured, add_entities = _capture_add_entities()

    # Explicitly disabled WSLINK
    config_entry.options[WSLINK] = False

    await async_setup_entry(hass, config_entry, add_entities)

    descriptions = hass.data["sws12500"][config_entry.entry_id][ENTRY_DESCRIPTIONS]
    assert set(descriptions.keys()) == {d.key for d in SENSOR_TYPES_WEATHER_API}
    assert captured == []


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_selects_wslink_descriptions_when_wslink_enabled(
    hass, config_entry
):
    hass.data.setdefault("sws12500", {})
    hass.data["sws12500"][config_entry.entry_id] = {
        ENTRY_COORDINATOR: _CoordinatorStub()
    }

    captured, add_entities = _capture_add_entities()

    config_entry.options[WSLINK] = True

    await async_setup_entry(hass, config_entry, add_entities)

    descriptions = hass.data["sws12500"][config_entry.entry_id][ENTRY_DESCRIPTIONS]
    assert set(descriptions.keys()) == {d.key for d in SENSOR_TYPES_WSLINK}
    assert captured == []


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_adds_requested_entities_and_auto_enables_derived(
    hass, config_entry
):
    hass.data.setdefault("sws12500", {})
    coordinator = _CoordinatorStub()
    hass.data["sws12500"][config_entry.entry_id] = {ENTRY_COORDINATOR: coordinator}

    captured, add_entities = _capture_add_entities()

    # Request WIND_DIR, OUTSIDE_TEMP, OUTSIDE_HUMIDITY, WIND_SPEED -> should auto-add derived keys too.
    config_entry.options[WSLINK] = False
    config_entry.options[SENSORS_TO_LOAD] = [
        WIND_DIR,
        OUTSIDE_TEMP,
        OUTSIDE_HUMIDITY,
        WIND_SPEED,
    ]

    await async_setup_entry(hass, config_entry, add_entities)

    # We should have at least those requested + derived in the added entities.
    keys_added = {
        e.entity_description.key for e in captured if isinstance(e, WeatherSensor)
    }
    assert WIND_DIR in keys_added
    assert OUTSIDE_TEMP in keys_added
    assert OUTSIDE_HUMIDITY in keys_added
    assert WIND_SPEED in keys_added

    # Derived:
    assert WIND_AZIMUT in keys_added
    assert HEAT_INDEX in keys_added
    assert CHILL_INDEX in keys_added


def test_add_new_sensors_is_noop_when_domain_missing(hass, config_entry):
    called = False

    def add_entities(_entities: list[Any]) -> None:
        nonlocal called
        called = True

    # No hass.data["sws12500"] at all.
    add_new_sensors(hass, config_entry, keys=["anything"])

    assert called is False


def test_add_new_sensors_is_noop_when_entry_missing(hass, config_entry):
    hass.data["sws12500"] = {}
    called = False

    def add_entities(_entities: list[Any]) -> None:
        nonlocal called
        called = True

    add_new_sensors(hass, config_entry, keys=["anything"])

    assert called is False


def test_add_new_sensors_is_noop_when_callback_or_descriptions_missing(
    hass, config_entry
):
    hass.data["sws12500"] = {
        config_entry.entry_id: {ENTRY_COORDINATOR: _CoordinatorStub()}
    }
    called = False

    def add_entities(_entities: list[Any]) -> None:
        nonlocal called
        called = True

    # Missing ENTRY_ADD_ENTITIES + ENTRY_DESCRIPTIONS -> no-op.
    add_new_sensors(hass, config_entry, keys=["anything"])

    assert called is False


def test_add_new_sensors_ignores_unknown_keys(hass, config_entry):
    hass.data["sws12500"] = {
        config_entry.entry_id: {
            ENTRY_COORDINATOR: _CoordinatorStub(),
            ENTRY_ADD_ENTITIES: MagicMock(),
            ENTRY_DESCRIPTIONS: {},  # nothing known
        }
    }

    add_new_sensors(hass, config_entry, keys=["unknown_key"])

    hass.data["sws12500"][config_entry.entry_id][ENTRY_ADD_ENTITIES].assert_not_called()


def test_add_new_sensors_adds_known_keys(hass, config_entry):
    coordinator = _CoordinatorStub()
    add_entities = MagicMock()

    # Use one known description from the weather API list.
    known_desc = SENSOR_TYPES_WEATHER_API[0]

    hass.data["sws12500"] = {
        config_entry.entry_id: {
            ENTRY_COORDINATOR: coordinator,
            ENTRY_ADD_ENTITIES: add_entities,
            ENTRY_DESCRIPTIONS: {known_desc.key: known_desc},
        }
    }

    add_new_sensors(hass, config_entry, keys=[known_desc.key])

    add_entities.assert_called_once()
    (entities_arg,) = add_entities.call_args.args
    assert isinstance(entities_arg, list)
    assert len(entities_arg) == 1
    assert isinstance(entities_arg[0], WeatherSensor)
    assert entities_arg[0].entity_description.key == known_desc.key
