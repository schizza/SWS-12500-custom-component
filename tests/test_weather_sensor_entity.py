from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import MagicMock

import pytest

from custom_components.sws12500.const import DOMAIN
from custom_components.sws12500.sensor import WeatherSensor


@dataclass(slots=True)
class _DescriptionStub:
    """Minimal stand-in for WeatherSensorEntityDescription.

    WeatherSensor only relies on:
    - key
    - value_fn
    - value_from_data_fn
    """

    key: str
    value_fn: Callable[[Any], Any] | None = None
    value_from_data_fn: Callable[[dict[str, Any]], Any] | None = None


class _CoordinatorStub:
    """Minimal coordinator stub used by WeatherSensor."""

    def __init__(
        self, data: dict[str, Any] | None = None, *, config: Any | None = None
    ):
        self.data = data if data is not None else {}
        self.config = config


def test_native_value_prefers_value_from_data_fn_success():
    desc = _DescriptionStub(
        key="derived",
        value_from_data_fn=lambda data: f"v:{data.get('x')}",
        value_fn=lambda raw: f"raw:{raw}",  # should not be used
    )
    coordinator = _CoordinatorStub(data={"x": 123, "derived": "ignored"})
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value == "v:123"


def test_native_value_value_from_data_fn_success_with_dev_logging_hits_computed_debug_branch(
    monkeypatch,
):
    """Cover the dev-log debug branch after successful value_from_data_fn computation."""
    debug = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.sensor._LOGGER.debug", debug)

    desc = _DescriptionStub(
        key="derived",
        value_from_data_fn=lambda data: data["x"] + 1,
    )
    config = SimpleNamespace(options={"dev_debug_checkbox": True})
    coordinator = _CoordinatorStub(data={"x": 41}, config=config)
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value == 42

    debug.assert_any_call(
        "native_value computed via value_from_data_fn: key=%s -> %s",
        "derived",
        42,
    )


def test_native_value_value_from_data_fn_exception_returns_none():
    def boom(_data: dict[str, Any]) -> Any:
        raise RuntimeError("nope")

    desc = _DescriptionStub(key="derived", value_from_data_fn=boom)
    coordinator = _CoordinatorStub(data={"derived": 1})
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value is None


def test_native_value_missing_raw_returns_none():
    desc = _DescriptionStub(key="missing", value_fn=lambda raw: raw)
    coordinator = _CoordinatorStub(data={})
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value is None


def test_native_value_missing_raw_with_dev_logging_hits_debug_branch(monkeypatch):
    monkeypatch.setattr(
        "custom_components.sws12500.sensor._LOGGER.debug", lambda *a, **k: None
    )

    desc = _DescriptionStub(key="missing", value_fn=lambda raw: raw)
    config = SimpleNamespace(options={"dev_debug_checkbox": True})
    coordinator = _CoordinatorStub(data={}, config=config)
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value is None


def test_native_value_raw_none_with_dev_logging_hits_debug_branch(monkeypatch):
    # This targets the `raw is None` branch (not empty string) and ensures the debug line
    # is actually executed (coverage sometimes won't attribute it when data is missing).
    called = {"debug": 0}

    def _debug(*_a, **_k):
        called["debug"] += 1

    monkeypatch.setattr("custom_components.sws12500.sensor._LOGGER.debug", _debug)

    desc = _DescriptionStub(key="k", value_fn=lambda raw: raw)
    config = SimpleNamespace(options={"dev_debug_checkbox": True})

    # Ensure the key exists and explicitly maps to None so `data.get(key)` returns None
    # in a deterministic way for coverage.
    coordinator = _CoordinatorStub(data={"k": None}, config=config)
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value is None
    assert called["debug"] >= 1


def test_native_value_missing_raw_logs_specific_message(monkeypatch):
    """Target the exact debug log line for missing raw values.

    This is meant to hit the specific `_LOGGER.debug("native_value missing raw: ...")`
    statement to help achieve full `sensor.py` coverage.
    """
    debug = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.sensor._LOGGER.debug", debug)

    desc = _DescriptionStub(key="k", value_fn=lambda raw: raw)
    config = SimpleNamespace(options={"dev_debug_checkbox": True})
    coordinator = _CoordinatorStub(data={"k": None}, config=config)

    entity = WeatherSensor(desc, coordinator)
    assert entity.native_value is None

    debug.assert_any_call("native_value missing raw: key=%s raw=%s", "k", None)


def test_native_value_empty_string_raw_returns_none():
    desc = _DescriptionStub(key="k", value_fn=lambda raw: raw)
    coordinator = _CoordinatorStub(data={"k": ""})
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value is None


def test_native_value_empty_string_raw_with_dev_logging_hits_debug_branch(monkeypatch):
    monkeypatch.setattr(
        "custom_components.sws12500.sensor._LOGGER.debug", lambda *a, **k: None
    )

    desc = _DescriptionStub(key="k", value_fn=lambda raw: raw)
    config = SimpleNamespace(options={"dev_debug_checkbox": True})
    coordinator = _CoordinatorStub(data={"k": ""}, config=config)
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value is None


def test_native_value_no_value_fn_returns_none():
    desc = _DescriptionStub(key="k", value_fn=None)
    coordinator = _CoordinatorStub(data={"k": 10})
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value is None


def test_native_value_no_value_fn_with_dev_logging_hits_debug_branch(monkeypatch):
    monkeypatch.setattr(
        "custom_components.sws12500.sensor._LOGGER.debug", lambda *a, **k: None
    )

    desc = _DescriptionStub(key="k", value_fn=None)
    config = SimpleNamespace(options={"dev_debug_checkbox": True})
    coordinator = _CoordinatorStub(data={"k": 10}, config=config)
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value is None


def test_native_value_value_fn_success():
    desc = _DescriptionStub(key="k", value_fn=lambda raw: int(raw) + 1)
    coordinator = _CoordinatorStub(data={"k": "41"})
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value == 42


def test_native_value_value_fn_success_with_dev_logging_hits_debug_branch(monkeypatch):
    monkeypatch.setattr(
        "custom_components.sws12500.sensor._LOGGER.debug", lambda *a, **k: None
    )

    desc = _DescriptionStub(key="k", value_fn=lambda raw: int(raw) + 1)
    config = SimpleNamespace(options={"dev_debug_checkbox": True})
    coordinator = _CoordinatorStub(data={"k": "41"}, config=config)
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value == 42


def test_native_value_value_fn_exception_returns_none():
    def boom(_raw: Any) -> Any:
        raise ValueError("bad")

    desc = _DescriptionStub(key="k", value_fn=boom)
    coordinator = _CoordinatorStub(data={"k": "x"})
    entity = WeatherSensor(desc, coordinator)

    assert entity.native_value is None


def test_suggested_entity_id_uses_sensor_domain_and_key(monkeypatch):
    # `homeassistant.helpers.entity.generate_entity_id` requires either `current_ids` or `hass`.
    # Our entity isn't attached to hass in this unit test, so patch it to a deterministic result.
    monkeypatch.setattr(
        "custom_components.sws12500.sensor.generate_entity_id",
        lambda _fmt, key: f"sensor.{key}",
    )

    desc = _DescriptionStub(key="outside_temp", value_fn=lambda raw: raw)
    coordinator = _CoordinatorStub(data={"outside_temp": 1})
    entity = WeatherSensor(desc, coordinator)

    suggested = entity.suggested_entity_id
    assert suggested == "sensor.outside_temp"


def test_device_info_contains_expected_identifiers_and_domain():
    desc = _DescriptionStub(key="k", value_fn=lambda raw: raw)
    coordinator = _CoordinatorStub(data={"k": 1})
    entity = WeatherSensor(desc, coordinator)

    info = entity.device_info
    assert info is not None
    # DeviceInfo is mapping-like; access defensively.
    assert info.get("name") == "Weather Station SWS 12500"
    assert info.get("manufacturer") == "Schizza"
    assert info.get("model") == "Weather Station SWS 12500"

    identifiers = info.get("identifiers")
    assert isinstance(identifiers, set)
    assert (DOMAIN,) in identifiers


def test_dev_log_flag_reads_from_config_entry_options():
    # When coordinator has a config with options, WeatherSensor should read dev_debug_checkbox.
    desc = _DescriptionStub(key="k", value_fn=lambda raw: raw)
    config = SimpleNamespace(options={"dev_debug_checkbox": True})
    coordinator = _CoordinatorStub(data={"k": 1}, config=config)
    entity = WeatherSensor(desc, coordinator)

    # We don't assert logs; we just ensure native_value still works with dev logging enabled.
    assert entity.native_value == 1
