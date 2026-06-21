"""Coverage tests for the health coordinator and health diagnostic sensors.

These tests exercise the runtime health model end to end without requiring real
network access. The add-on reachability check in `_async_update_data` is the only
network-bound path; it is covered by monkeypatching the aiohttp session factory
and the network helpers (`async_get_source_ip`, `get_url`).

Architecture notes (see CRITICAL ARCHITECTURE NOTES in the task brief):
- `HealthCoordinator(hass, config)` forwards `config_entry=config` to
  `DataUpdateCoordinator.__init__`, which calls `config.async_on_unload(...)`.
  A `MockConfigEntry` supports that, so we always pass one.
- Health persistence writes `config.runtime_data.health_data`; we set
  `entry.runtime_data` to a real `SWSRuntimeData` to cover the success path and
  also test the `AttributeError` branch when it is missing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
from aiohttp import ClientConnectionError
from aiohttp.web_exceptions import HTTPUnauthorized
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sws12500 import health_coordinator as hc, health_sensor as hs
from custom_components.sws12500.const import (
    DEFAULT_URL,
    DOMAIN,
    ECOWITT_ENABLED,
    ECOWITT_URL_PREFIX,
    HEALTH_URL,
    LEGACY_ENABLED,
    POCASI_CZ_ENABLED,
    WINDY_ENABLED,
    WSLINK,
    WSLINK_ADDON_PORT,
    WSLINK_URL,
)
from custom_components.sws12500.data import SWSRuntimeData
from custom_components.sws12500.health_coordinator import HealthCoordinator
from custom_components.sws12500.routes import Routes
from homeassistant.components.http import KEY_AUTHENTICATED

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_entry(options: dict[str, Any] | None = None) -> MockConfigEntry:
    """Create a config entry usable by the coordinator constructor."""
    return MockConfigEntry(domain=DOMAIN, data={}, options=options or {})


@pytest.fixture
def entry() -> MockConfigEntry:
    """A config entry with empty options."""
    return _make_entry()


def _attach_runtime_data(entry: MockConfigEntry, coordinator: HealthCoordinator) -> None:
    """Attach a real SWSRuntimeData so the persistence success path is exercised."""
    entry.runtime_data = SWSRuntimeData(
        coordinator=MagicMock(),
        health_coordinator=coordinator,
        last_options={},
    )


class _FakeResponse:
    """Minimal aiohttp-like response."""

    def __init__(self, status: int, json_data: Any = None, json_exc: Exception | None = None) -> None:
        self.status = status
        self._json_data = json_data
        self._json_exc = json_exc

    async def json(self, content_type: Any = None) -> Any:  # noqa: ARG002 - signature match
        if self._json_exc is not None:
            raise self._json_exc
        return self._json_data


class _FakeSession:
    """Fake aiohttp session whose `.get()` returns an async context manager.

    `responses` maps a URL substring to either a `_FakeResponse` or an Exception
    that should be raised when entering the context manager.
    """

    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses

    def get(self, url: str):  # noqa: D401 - mimic aiohttp
        outcome: Any = None
        for needle, value in self._responses.items():
            if needle in url:
                outcome = value
                break

        @asynccontextmanager
        async def _ctx():
            if isinstance(outcome, Exception):
                raise outcome
            yield outcome

        return _ctx()


def _patch_network(monkeypatch, session: _FakeSession, ip: str = "1.2.3.4") -> None:
    """Patch the coordinator network helpers to deterministic values."""
    monkeypatch.setattr(hc, "async_get_clientsession", lambda _hass, _verify=False: session)
    monkeypatch.setattr(hc, "async_get_source_ip", AsyncMock(return_value=ip))
    monkeypatch.setattr(hc, "get_url", lambda _hass: "http://ha:8123")


# ---------------------------------------------------------------------------
# Module-level helpers in health_coordinator.py
# ---------------------------------------------------------------------------


def test_configured_protocol() -> None:
    # Legacy enabled (default) -> wu / wslink based on the WSLINK flag.
    assert hc._configured_protocol(_make_entry()) == "wu"
    assert hc._configured_protocol(_make_entry({WSLINK: True})) == "wslink"
    # Ecowitt-only (legacy off, ecowitt on) -> ecowitt.
    assert hc._configured_protocol(_make_entry({LEGACY_ENABLED: False, ECOWITT_ENABLED: True})) == "ecowitt"
    # Nothing configured -> wu fallback.
    assert hc._configured_protocol(_make_entry({LEGACY_ENABLED: False, ECOWITT_ENABLED: False})) == "wu"


def test_protocol_from_path_all_branches() -> None:
    assert hc._protocol_from_path(WSLINK_URL) == "wslink"
    assert hc._protocol_from_path(DEFAULT_URL) == "wu"
    assert hc._protocol_from_path(HEALTH_URL) == "health"
    assert hc._protocol_from_path(ECOWITT_URL_PREFIX + "/abc") == "ecowitt"
    assert hc._protocol_from_path("/something/else") == "unknown"


def test_empty_forwarding_state() -> None:
    enabled = hc._empty_forwarding_state(True)
    assert enabled == {
        "enabled": True,
        "last_status": "idle",
        "last_error": None,
        "last_attempt_at": None,
    }
    disabled = hc._empty_forwarding_state(False)
    assert disabled["enabled"] is False
    assert disabled["last_status"] == "disabled"


def test_default_health_data() -> None:
    entry = _make_entry({WSLINK: True, WINDY_ENABLED: True, POCASI_CZ_ENABLED: False})
    data = hc._default_health_data(entry)

    assert data["configured_protocol"] == "wslink"
    assert data["active_protocol"] == "wslink"
    assert data["integration_status"] == "online_wslink"
    assert data["addon"]["online"] is False
    assert data["addon"]["paths"] == {"wslink": WSLINK_URL, "wu": DEFAULT_URL}
    assert data["forwarding"]["windy"]["enabled"] is True
    assert data["forwarding"]["pocasi"]["enabled"] is False
    assert data["last_ingress"]["reason"] == "no_data"


def test_default_health_data_wu_default() -> None:
    data = hc._default_health_data(_make_entry())
    assert data["configured_protocol"] == "wu"
    assert data["integration_status"] == "online_wu"


def test_default_health_data_ecowitt() -> None:
    data = hc._default_health_data(_make_entry({LEGACY_ENABLED: False, ECOWITT_ENABLED: True}))
    assert data["configured_protocol"] == "ecowitt"
    assert data["active_protocol"] == "ecowitt"
    assert data["integration_status"] == "online_ecowitt"


# ---------------------------------------------------------------------------
# HealthCoordinator construction & persistence
# ---------------------------------------------------------------------------


def test_store_runtime_health_success(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    payload = {"hello": "world"}
    coordinator._store_runtime_health(payload)

    assert entry.runtime_data.health_data == payload
    # deepcopy: stored value is independent of the source dict
    assert entry.runtime_data.health_data is not payload


def test_store_runtime_health_missing_runtime_data(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    # entry.runtime_data is unset -> AttributeError branch must be swallowed.
    assert getattr(entry, "runtime_data", None) is None
    coordinator._store_runtime_health({"a": 1})  # must not raise


def test_commit_publishes_and_persists(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    new_data = hc._default_health_data(entry)
    new_data["integration_status"] = "custom"

    result = coordinator._commit(new_data)

    assert result is new_data
    assert coordinator.data["integration_status"] == "custom"
    assert entry.runtime_data.health_data["integration_status"] == "custom"


# ---------------------------------------------------------------------------
# _refresh_summary branches
# ---------------------------------------------------------------------------


def test_refresh_summary_degraded_by_reason(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    data = hc._default_health_data(entry)
    data["configured_protocol"] = "wu"
    data["last_ingress"] = {"protocol": "wu", "accepted": False, "reason": "route_disabled"}

    coordinator._refresh_summary(data)

    assert data["integration_status"] == "degraded"
    # not accepted -> active falls back to configured protocol
    assert data["active_protocol"] == "wu"


def test_refresh_summary_degraded_by_protocol_mismatch(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    data = hc._default_health_data(entry)
    data["configured_protocol"] = "wu"
    # last protocol differs from configured -> degraded even when accepted
    data["last_ingress"] = {"protocol": "wslink", "accepted": True, "reason": "accepted"}

    coordinator._refresh_summary(data)

    assert data["integration_status"] == "degraded"
    # accepted + recognized protocol -> active protocol tracks the ingress
    assert data["active_protocol"] == "wslink"


def test_refresh_summary_online_protocol(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    data = hc._default_health_data(entry)
    data["configured_protocol"] = "wslink"
    data["last_ingress"] = {"protocol": "wslink", "accepted": True, "reason": "accepted"}

    coordinator._refresh_summary(data)

    assert data["integration_status"] == "online_wslink"
    assert data["active_protocol"] == "wslink"


def test_refresh_summary_online_idle(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    data = hc._default_health_data(entry)
    data["configured_protocol"] = "wu"
    data["last_ingress"] = {"protocol": "unknown", "accepted": False, "reason": "no_data"}

    coordinator._refresh_summary(data)

    assert data["integration_status"] == "online_idle"
    assert data["active_protocol"] == "wu"


def test_refresh_summary_online_ecowitt(hass, entry) -> None:
    # Ecowitt ingress is a valid protocol: active_protocol must track it (not fall back
    # to the legacy "wu"), and it must not be flagged as a WU/WSLink mismatch.
    coordinator = HealthCoordinator(hass, entry)
    data = hc._default_health_data(entry)
    data["configured_protocol"] = "wu"
    data["last_ingress"] = {"protocol": "ecowitt", "accepted": True, "reason": "accepted"}

    coordinator._refresh_summary(data)

    assert data["integration_status"] == "online_ecowitt"
    assert data["active_protocol"] == "ecowitt"


# ---------------------------------------------------------------------------
# _async_update_data: offline and online paths
# ---------------------------------------------------------------------------


async def test_async_update_data_addon_offline(hass, monkeypatch) -> None:
    entry = _make_entry({WSLINK_ADDON_PORT: 8443})
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    session = _FakeSession({"/healthz": ClientConnectionError("boom")})
    _patch_network(monkeypatch, session)

    data = await coordinator._async_update_data()

    addon = data["addon"]
    assert addon["online"] is False
    assert addon["health_url"] == "https://1.2.3.4:8443/healthz"
    assert addon["info_url"] == "https://1.2.3.4:8443/status/internal"
    assert addon["home_assistant_url"] == "http://ha:8123"
    assert addon["home_assistant_source_ip"] == "1.2.3.4"
    assert addon["raw_status"] is None
    assert addon["name"] is None


async def test_async_update_data_addon_online(hass, monkeypatch) -> None:
    entry = _make_entry()  # no WSLINK_ADDON_PORT -> default 443
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    raw_status = {
        "addon": "wslink-addon",
        "version": "1.2.3",
        "listen": {"port": 8443, "tls": True},
        "upstream": {"ha_port": 8123},
        "paths": {"wslink": "/custom/wslink", "wu": "/custom/wu"},
    }
    session = _FakeSession(
        {
            "/healthz": _FakeResponse(200),
            "/status/internal": _FakeResponse(200, json_data=raw_status),
        }
    )
    _patch_network(monkeypatch, session)

    data = await coordinator._async_update_data()

    addon = data["addon"]
    assert addon["online"] is True
    assert addon["health_url"] == "https://1.2.3.4:443/healthz"
    assert addon["name"] == "wslink-addon"
    assert addon["version"] == "1.2.3"
    assert addon["listen_port"] == 8443
    assert addon["tls"] is True
    assert addon["upstream_ha_port"] == 8123
    assert addon["paths"] == {"wslink": "/custom/wslink", "wu": "/custom/wu"}
    assert addon["raw_status"] == raw_status


async def test_async_update_data_info_endpoint_value_error(hass, monkeypatch) -> None:
    """Online add-on but the info endpoint returns invalid JSON."""
    entry = _make_entry()
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    info_resp = _FakeResponse(200, json_exc=ValueError("bad json"))
    session = _FakeSession(
        {
            "/healthz": _FakeResponse(200),
            "/status/internal": info_resp,
        }
    )
    _patch_network(monkeypatch, session)

    data = await coordinator._async_update_data()

    addon = data["addon"]
    assert addon["online"] is True
    assert addon["raw_status"] is None
    # raw_status falsy -> add-on metadata stays at defaults
    assert addon["name"] is None
    assert addon["version"] is None


async def test_async_update_data_info_non_200(hass, monkeypatch) -> None:
    """Online add-on but info endpoint replies non-200 -> raw_status stays None."""
    entry = _make_entry()
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    session = _FakeSession(
        {
            "/healthz": _FakeResponse(200),
            "/status/internal": _FakeResponse(503),
        }
    )
    _patch_network(monkeypatch, session)

    data = await coordinator._async_update_data()
    assert data["addon"]["online"] is True
    assert data["addon"]["raw_status"] is None


# ---------------------------------------------------------------------------
# update_routing
# ---------------------------------------------------------------------------


def test_update_routing_none(hass) -> None:
    entry = _make_entry({WSLINK: True})
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    coordinator.update_routing(None)

    assert coordinator.data["configured_protocol"] == "wslink"
    # routes block unchanged from default when None passed
    assert coordinator.data["routes"]["wu_enabled"] is False


def test_update_routing_with_routes(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    routes = Routes()
    coordinator.update_routing(routes)

    routes_block = coordinator.data["routes"]
    assert routes_block["wu_enabled"] is False
    assert routes_block["wslink_enabled"] is False
    assert routes_block["health_enabled"] is False
    assert routes_block["snapshot"] == {}


# ---------------------------------------------------------------------------
# record_dispatch
# ---------------------------------------------------------------------------


def test_record_dispatch_skips_health(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)
    before = coordinator.data["last_ingress"].copy()

    request = SimpleNamespace(path=HEALTH_URL, method="GET")
    coordinator.record_dispatch(request, route_enabled=True, reason=None)

    # health path is ignored -> last_ingress untouched
    assert coordinator.data["last_ingress"] == before


def test_record_dispatch_records(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    request = SimpleNamespace(path=WSLINK_URL, method="POST")
    coordinator.record_dispatch(request, route_enabled=True, reason=None)

    ingress = coordinator.data["last_ingress"]
    assert ingress["protocol"] == "wslink"
    assert ingress["path"] == WSLINK_URL
    assert ingress["method"] == "POST"
    assert ingress["route_enabled"] is True
    assert ingress["accepted"] is False
    assert ingress["reason"] == "pending"
    assert ingress["time"] is not None


def test_record_dispatch_records_with_reason(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    request = SimpleNamespace(path=DEFAULT_URL, method="GET")
    coordinator.record_dispatch(request, route_enabled=False, reason="route_disabled")

    ingress = coordinator.data["last_ingress"]
    assert ingress["reason"] == "route_disabled"
    # route_disabled reason makes the summary degraded
    assert coordinator.data["integration_status"] == "degraded"


def test_record_dispatch_masks_ecowitt_webhook_id(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    request = SimpleNamespace(path=ECOWITT_URL_PREFIX + "/supersecretid", method="POST")
    coordinator.record_dispatch(request, route_enabled=True, reason=None)

    ingress = coordinator.data["last_ingress"]
    assert ingress["protocol"] == "ecowitt"
    # The secret webhook id must never reach the (potentially exposed) snapshot.
    assert ingress["path"] == ECOWITT_URL_PREFIX + "/***"
    assert "supersecretid" not in ingress["path"]


# ---------------------------------------------------------------------------
# update_ingress_result
# ---------------------------------------------------------------------------


def test_update_ingress_result_accepted(hass) -> None:
    entry = _make_entry({WSLINK: True})
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    request = SimpleNamespace(path=WSLINK_URL, method="POST")
    coordinator.update_ingress_result(request, accepted=True, authorized=True)

    ingress = coordinator.data["last_ingress"]
    assert ingress["accepted"] is True
    assert ingress["authorized"] is True
    assert ingress["reason"] == "accepted"
    assert ingress["protocol"] == "wslink"
    assert coordinator.data["integration_status"] == "online_wslink"


def test_update_ingress_result_rejected_default_reason(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    request = SimpleNamespace(path=DEFAULT_URL, method="GET")
    coordinator.update_ingress_result(request, accepted=False, authorized=False)

    ingress = coordinator.data["last_ingress"]
    assert ingress["accepted"] is False
    assert ingress["reason"] == "rejected"


def test_update_ingress_result_explicit_reason(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    request = SimpleNamespace(path=DEFAULT_URL, method="GET")
    coordinator.update_ingress_result(
        request, accepted=False, authorized=None, reason="unauthorized"
    )

    assert coordinator.data["last_ingress"]["reason"] == "unauthorized"
    assert coordinator.data["integration_status"] == "degraded"


# ---------------------------------------------------------------------------
# update_forwarding
# ---------------------------------------------------------------------------


def test_update_forwarding(hass, entry) -> None:
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    windy = SimpleNamespace(
        enabled=True, last_status="ok", last_error=None, last_attempt_at="2026-06-20T10:00:00"
    )
    pocasi = SimpleNamespace(
        enabled=False, last_status="disabled", last_error="oops", last_attempt_at=None
    )

    coordinator.update_forwarding(windy, pocasi)

    forwarding = coordinator.data["forwarding"]
    assert forwarding["windy"] == {
        "enabled": True,
        "last_status": "ok",
        "last_error": None,
        "last_attempt_at": "2026-06-20T10:00:00",
    }
    assert forwarding["pocasi"]["last_error"] == "oops"


# ---------------------------------------------------------------------------
# health_status HTTP endpoint
# ---------------------------------------------------------------------------


async def test_health_status_endpoint_authenticated(hass, entry, monkeypatch) -> None:
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    # Avoid network: stub the refresh that health_status awaits.
    monkeypatch.setattr(coordinator, "async_request_refresh", AsyncMock(return_value=None))

    # aiohttp Request is dict-like; health_status only reads KEY_AUTHENTICATED.
    request = {KEY_AUTHENTICATED: True}
    response = await coordinator.health_status(request)  # type: ignore[arg-type]

    assert isinstance(response, aiohttp.web.Response)
    assert response.status == 200
    coordinator.async_request_refresh.assert_awaited_once()


async def test_health_status_endpoint_rejects_unauthenticated(hass, entry, monkeypatch) -> None:
    coordinator = HealthCoordinator(hass, entry)
    _attach_runtime_data(entry, coordinator)

    refresh = AsyncMock(return_value=None)
    monkeypatch.setattr(coordinator, "async_request_refresh", refresh)

    # No KEY_AUTHENTICATED flag -> unauthenticated -> 401, no refresh triggered.
    with pytest.raises(HTTPUnauthorized):
        await coordinator.health_status({})  # type: ignore[arg-type]

    refresh.assert_not_awaited()


# ---------------------------------------------------------------------------
# health_sensor.py module helpers
# ---------------------------------------------------------------------------


def test_resolve_path_nested() -> None:
    data = {"addon": {"online": True}}
    assert hs._resolve_path(data, ("addon", "online")) is True


def test_resolve_path_missing_key() -> None:
    data = {"addon": {}}
    assert hs._resolve_path(data, ("addon", "missing")) is None


def test_resolve_path_intermediate_not_dict() -> None:
    # Intermediate value is not a dict -> _resolve_path returns None.
    data = {"addon": "not-a-dict"}
    assert hs._resolve_path(data, ("addon", "online")) is None


def test_on_off() -> None:
    assert hs._on_off(True) == "on"
    assert hs._on_off(False) == "off"
    assert hs._on_off(None) == "off"


def test_accepted_state() -> None:
    assert hs._accepted_state(True) == "accepted"
    assert hs._accepted_state(False) == "rejected"


def test_authorized_state() -> None:
    assert hs._authorized_state(None) == "unknown"
    assert hs._authorized_state(True) == "authorized"
    assert hs._authorized_state(False) == "unauthorized"


def test_timestamp_or_none() -> None:
    assert hs._timestamp_or_none(123) is None
    assert hs._timestamp_or_none(None) is None
    parsed = hs._timestamp_or_none("2026-06-20T10:00:00+00:00")
    assert isinstance(parsed, datetime)


# ---------------------------------------------------------------------------
# health_sensor.py async_setup_entry
# ---------------------------------------------------------------------------


async def test_async_setup_entry_creates_sensors(hass, entry) -> None:
    coordinator = MagicMock()
    coordinator.data = {}
    entry.runtime_data = SWSRuntimeData(
        coordinator=MagicMock(),
        health_coordinator=coordinator,
        last_options={},
    )

    added: list[Any] = []

    def _add_entities(entities: Any) -> None:
        added.extend(entities)

    await hs.async_setup_entry(hass, entry, _add_entities)

    assert len(added) == len(hs.HEALTH_SENSOR_DESCRIPTIONS)
    assert all(isinstance(sensor, hs.HealthDiagnosticSensor) for sensor in added)


# ---------------------------------------------------------------------------
# HealthDiagnosticSensor
# ---------------------------------------------------------------------------


def _description(key: str) -> hs.HealthSensorEntityDescription:
    """Return the bundled description for `key`."""
    return next(d for d in hs.HEALTH_SENSOR_DESCRIPTIONS if d.key == key)


def _stub_coordinator(data: dict[str, Any]) -> Any:
    """CoordinatorEntity.__init__ only stores the coordinator; a stub suffices."""
    return SimpleNamespace(data=data)


def test_sensor_native_value_without_value_fn() -> None:
    coordinator = _stub_coordinator({"integration_status": "online_wu"})
    sensor = hs.HealthDiagnosticSensor(coordinator, _description("integration_health"))
    assert sensor.native_value == "online_wu"


def test_sensor_native_value_with_value_fn() -> None:
    coordinator = _stub_coordinator({"addon": {"online": True}})
    sensor = hs.HealthDiagnosticSensor(coordinator, _description("wslink_addon_status"))
    assert sensor.native_value == "online"


def test_sensor_extra_state_attributes_strips_internal_fields() -> None:
    data = {
        "integration_status": "online_wu",
        "addon": {
            "online": True,
            "name": "wslink_proxy",
            "home_assistant_source_ip": "1.2.3.4",
            "health_url": "https://1.2.3.4:443/healthz",
            "info_url": "https://1.2.3.4:443/status/internal",
            "home_assistant_url": "http://ha:8123",
            "raw_status": {"secret": "x"},
        },
    }
    coordinator = _stub_coordinator(data)
    sensor = hs.HealthDiagnosticSensor(coordinator, _description("integration_health"))

    attrs = sensor.extra_state_attributes
    assert attrs is not None
    # Non-sensitive fields pass through.
    assert attrs["integration_status"] == "online_wu"
    assert attrs["addon"]["online"] is True
    assert attrs["addon"]["name"] == "wslink_proxy"
    # Internal network details are stripped from the (any-user-readable) attributes.
    for field in ("home_assistant_source_ip", "health_url", "info_url", "home_assistant_url", "raw_status"):
        assert field not in attrs["addon"]
    # The source snapshot is not mutated (deepcopy).
    assert "raw_status" in data["addon"]


def test_sensor_extra_state_attributes_none_data() -> None:
    coordinator = _stub_coordinator(None)
    sensor = hs.HealthDiagnosticSensor(coordinator, _description("integration_health"))
    assert sensor.extra_state_attributes is None


def test_sensor_extra_state_attributes_for_other_keys() -> None:
    coordinator = _stub_coordinator({"active_protocol": "wu"})
    sensor = hs.HealthDiagnosticSensor(coordinator, _description("active_protocol"))
    assert sensor.extra_state_attributes is None


def test_public_health_snapshot_handles_missing_or_nondict_addon() -> None:
    # addon missing -> returned as-is (copy).
    assert hc.public_health_snapshot({"integration_status": "x"}) == {"integration_status": "x"}
    # addon not a dict -> left untouched.
    assert hc.public_health_snapshot({"addon": "nope"}) == {"addon": "nope"}


def test_sensor_device_info() -> None:
    coordinator = _stub_coordinator({})
    sensor = hs.HealthDiagnosticSensor(coordinator, _description("active_protocol"))
    info = sensor.device_info
    assert info["name"] == "Weather Station SWS 12500"
    assert info["manufacturer"] == "Schizza"
    assert info["model"] == "Weather Station SWS 12500"


def test_sensor_unique_id_and_category() -> None:
    coordinator = _stub_coordinator({})
    sensor = hs.HealthDiagnosticSensor(coordinator, _description("active_protocol"))
    assert sensor.unique_id == "active_protocol_health"
    assert sensor.entity_category == hs.EntityCategory.DIAGNOSTIC
