"""Tests for the typed per-entry runtime data container."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.sws12500.const import DOMAIN, ECOWITT_ENABLED, WSLINK
from custom_components.sws12500.data import (
    SWSRuntimeData,
    _station_model,
    build_device_info,
)


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


# --------------------------------------------------------------------------- #
# _station_model / build_device_info (single shared device)
# --------------------------------------------------------------------------- #


def test_station_model_pws_when_no_flags():
    """No ecowitt / wslink flags -> the legacy PWS push station."""
    entry = SimpleNamespace(options={})
    assert _station_model(entry) == "PWS"  # type: ignore[arg-type]


def test_station_model_wslink_when_flag_set():
    """The WSLINK flag (without ecowitt) yields the WSLink model."""
    entry = SimpleNamespace(options={WSLINK: True})
    assert _station_model(entry) == "WSLink"  # type: ignore[arg-type]


def test_station_model_ecowitt_without_learned_model():
    """Ecowitt enabled but no model learned yet -> bare "Ecowitt".

    Covers both the missing-runtime_data and the model-is-None paths.
    """
    no_runtime = SimpleNamespace(options={ECOWITT_ENABLED: True})
    assert _station_model(no_runtime) == "Ecowitt"  # type: ignore[arg-type]

    runtime_no_model = SimpleNamespace(
        options={ECOWITT_ENABLED: True},
        runtime_data=SimpleNamespace(ecowitt_model=None),
    )
    assert _station_model(runtime_no_model) == "Ecowitt"  # type: ignore[arg-type]


def test_station_model_ecowitt_with_learned_model():
    """Ecowitt enabled with a learned model -> "Ecowitt <model>"."""
    entry = SimpleNamespace(
        options={ECOWITT_ENABLED: True},
        runtime_data=SimpleNamespace(ecowitt_model="GW1000"),
    )
    assert _station_model(entry) == "Ecowitt GW1000"  # type: ignore[arg-type]


def test_station_model_ecowitt_takes_precedence_over_wslink():
    """When both flags are set the ecowitt model wins."""
    entry = SimpleNamespace(
        options={ECOWITT_ENABLED: True, WSLINK: True},
        runtime_data=SimpleNamespace(ecowitt_model="WS3900"),
    )
    assert _station_model(entry) == "Ecowitt WS3900"  # type: ignore[arg-type]


def test_build_device_info_shared_identity():
    """All entities share one device under the legacy ``{(DOMAIN,)}`` identifier."""
    entry = SimpleNamespace(options={})
    info = build_device_info(entry)  # type: ignore[arg-type]

    assert info["identifiers"] == {(DOMAIN,)}
    assert info["name"] == "Weather Station SWS 12500"
    assert info["manufacturer"] == "Schizza"
    assert info["model"] == "PWS"
