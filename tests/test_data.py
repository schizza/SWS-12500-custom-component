"""Tests for the typed per-entry runtime data container."""

from __future__ import annotations

from custom_components.sws12500.data import SWSRuntimeData


def test_runtime_data_defaults():
    """SWSRuntimeData exposes the expected fields with safe defaults.

    The ad-hoc hass.data[DOMAIN][entry_id] string keys (ENTRY_*) were replaced by
    this typed dataclass stored on entry.runtime_data in v2.0.
    """
    runtime = SWSRuntimeData(
        coordinator=object(),  # type: ignore[arg-type]
        health_coordinator=object(),  # type: ignore[arg-type]
        last_options={"legacy_enabled": True},
    )

    assert runtime.last_options == {"legacy_enabled": True}

    # Optional platform wiring defaults.
    assert runtime.add_sensor_entities is None
    assert runtime.sensor_descriptions == {}
    assert runtime.add_binary_entities is None
    assert runtime.binary_descriptions == {}
    assert runtime.added_binary_keys == set()

    # Diagnostics / staleness defaults.
    assert runtime.health_data is None
    assert runtime.last_seen == {}
    assert runtime.started_at is not None


def test_runtime_data_collections_are_independent_per_instance():
    """Mutable defaults must not be shared between instances."""
    a = SWSRuntimeData(coordinator=object(), health_coordinator=object(), last_options={})  # type: ignore[arg-type]
    b = SWSRuntimeData(coordinator=object(), health_coordinator=object(), last_options={})  # type: ignore[arg-type]

    a.sensor_descriptions["x"] = object()  # type: ignore[assignment]
    a.added_binary_keys.add("y")
    a.last_seen["z"] = object()  # type: ignore[assignment]

    assert b.sensor_descriptions == {}
    assert b.added_binary_keys == set()
    assert b.last_seen == {}
