from __future__ import annotations

from types import SimpleNamespace
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
from custom_components.sws12500.data import SWSRuntimeData
from custom_components.sws12500.sensor import (
    WeatherSensor,
    _auto_enable_derived_sensors,
    add_new_sensors,
    async_setup_entry,
)
from custom_components.sws12500.sensors_weather import SENSOR_TYPES_WEATHER_API
from custom_components.sws12500.sensors_wslink import SENSOR_TYPES_WSLINK


class _EcowittBridgeStub:
    """Records the platform callback the sensor setup wires into the bridge."""

    def __init__(self) -> None:
        self.add_entities_cb: Any = None

    def set_add_entities(self, callback: Any) -> None:
        self.add_entities_cb = callback


class _CoordinatorStub:
    """Minimal coordinator stub for WeatherSensor and platform setup."""

    def __init__(self, data: dict[str, Any] | None = None, *, options: dict[str, Any] | None = None) -> None:
        self.data = data if data is not None else {}
        # WeatherSensor.__init__ reads coordinator.config.options for the dev-log flag.
        self.config = SimpleNamespace(options=options if options is not None else {})
        self.ecowitt_bridge = _EcowittBridgeStub()


class _HealthCoordinatorStub:
    """Stand-in for HealthCoordinator (health diagnostic sensors subscribe to it)."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}


def _make_entry(
    *, options: dict[str, Any] | None = None, coordinator: _CoordinatorStub | None = None
) -> tuple[Any, _CoordinatorStub, SWSRuntimeData]:
    """Build a config-entry stub carrying typed runtime_data, like the integration does."""
    coordinator = coordinator or _CoordinatorStub()
    runtime = SWSRuntimeData(
        coordinator=coordinator,  # type: ignore[arg-type]
        health_coordinator=_HealthCoordinatorStub(),  # type: ignore[arg-type]
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
    # Sensor platform setup only forwards hass to health_sensor.async_setup_entry,
    # which ignores it, and add_new_sensors deletes it. A tiny stub is enough.
    class _Hass:
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}

    return _Hass()


def _capture_add_entities():
    captured: list[Any] = []

    def _add_entities(entities: list[Any]) -> None:
        captured.extend(entities)

    return captured, _add_entities


def _weather_keys(captured: list[Any]) -> set[str]:
    return {e.entity_description.key for e in captured if isinstance(e, WeatherSensor)}


# --- _auto_enable_derived_sensors ------------------------------------------


def test_auto_enable_derived_sensors_wind_azimut():
    expanded = _auto_enable_derived_sensors({WIND_DIR})
    assert WIND_DIR in expanded
    assert WIND_AZIMUT in expanded


def test_auto_enable_derived_sensors_heat_index():
    expanded = _auto_enable_derived_sensors({OUTSIDE_TEMP, OUTSIDE_HUMIDITY})
    assert HEAT_INDEX in expanded


def test_auto_enable_derived_sensors_chill_index():
    expanded = _auto_enable_derived_sensors({OUTSIDE_TEMP, WIND_SPEED})
    assert CHILL_INDEX in expanded


# --- async_setup_entry -----------------------------------------------------


@pytest.mark.asyncio
async def test_setup_stores_callback_and_descriptions_even_without_sensors_to_load(hass):
    entry, coordinator, runtime = _make_entry()
    captured, add_entities = _capture_add_entities()

    await async_setup_entry(hass, entry, add_entities)

    # Callback + description map persisted for dynamic entity creation.
    assert runtime.add_sensor_entities is add_entities
    assert isinstance(runtime.sensor_descriptions, dict)
    # Ecowitt bridge wired up even though there are no sensors to load yet.
    assert coordinator.ecowitt_bridge.add_entities_cb is add_entities
    # No weather sensors created (only health diagnostics, which we ignore here).
    assert _weather_keys(captured) == set()


@pytest.mark.asyncio
async def test_setup_selects_weather_api_descriptions_when_wslink_disabled(hass):
    entry, _coordinator, runtime = _make_entry(options={WSLINK: False})
    _captured, add_entities = _capture_add_entities()

    await async_setup_entry(hass, entry, add_entities)

    assert set(runtime.sensor_descriptions.keys()) == {d.key for d in SENSOR_TYPES_WEATHER_API}


@pytest.mark.asyncio
async def test_setup_selects_wslink_descriptions_when_wslink_enabled(hass):
    entry, _coordinator, runtime = _make_entry(options={WSLINK: True})
    _captured, add_entities = _capture_add_entities()

    await async_setup_entry(hass, entry, add_entities)

    assert set(runtime.sensor_descriptions.keys()) == {d.key for d in SENSOR_TYPES_WSLINK}


@pytest.mark.asyncio
async def test_setup_adds_requested_entities_and_auto_enables_derived(hass):
    entry, _coordinator, _runtime = _make_entry(
        options={
            WSLINK: False,
            SENSORS_TO_LOAD: [WIND_DIR, OUTSIDE_TEMP, OUTSIDE_HUMIDITY, WIND_SPEED],
        }
    )
    captured, add_entities = _capture_add_entities()

    await async_setup_entry(hass, entry, add_entities)

    keys_added = _weather_keys(captured)
    # Requested.
    assert {WIND_DIR, OUTSIDE_TEMP, OUTSIDE_HUMIDITY, WIND_SPEED} <= keys_added
    # Derived.
    assert {WIND_AZIMUT, HEAT_INDEX, CHILL_INDEX} <= keys_added


# --- add_new_sensors -------------------------------------------------------


def test_add_new_sensors_is_noop_when_callback_missing(hass):
    entry, _coordinator, runtime = _make_entry()
    # Platform not set up yet -> no stored callback.
    assert runtime.add_sensor_entities is None

    # Must not raise.
    add_new_sensors(hass, entry, keys=["anything"])


def test_add_new_sensors_ignores_unknown_keys(hass):
    entry, _coordinator, runtime = _make_entry()
    add_entities = MagicMock()
    runtime.add_sensor_entities = add_entities
    runtime.sensor_descriptions = {}  # nothing known

    add_new_sensors(hass, entry, keys=["unknown_key"])

    add_entities.assert_not_called()


def test_add_new_sensors_adds_known_keys(hass):
    entry, _coordinator, runtime = _make_entry()
    add_entities = MagicMock()
    known_desc = SENSOR_TYPES_WEATHER_API[0]
    runtime.add_sensor_entities = add_entities
    runtime.sensor_descriptions = {known_desc.key: known_desc}

    add_new_sensors(hass, entry, keys=[known_desc.key])

    add_entities.assert_called_once()
    (entities_arg,) = add_entities.call_args.args
    assert isinstance(entities_arg, list)
    assert len(entities_arg) == 1
    assert isinstance(entities_arg[0], WeatherSensor)
    assert entities_arg[0].entity_description.key == known_desc.key
