from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiohttp.web_exceptions import HTTPUnauthorized
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sws12500 import async_setup_entry, async_unload_entry, register_path, update_listener
from custom_components.sws12500.const import (
    API_ID,
    API_KEY,
    DEFAULT_URL,
    DOMAIN,
    ECOWITT_URL_PREFIX,
    HEALTH_URL,
    SENSORS_TO_LOAD,
    WSLINK,
    WSLINK_URL,
)
from custom_components.sws12500.coordinator import IncorrectDataError, WeatherDataUpdateCoordinator
from custom_components.sws12500.data import SWSRuntimeData
from custom_components.sws12500.health_coordinator import HealthCoordinator

ECOWITT_PATH = ECOWITT_URL_PREFIX + "/{webhook_id}"


@dataclass(slots=True)
class _RequestStub:
    """Minimal aiohttp Request stub used by `received_data`."""

    query: dict[str, Any]

    async def post(self) -> dict[str, Any]:
        return {}


class _RouterStub:
    """Router stub that records route registrations."""

    def __init__(self) -> None:
        self.add_get_calls: list[tuple[str, Any]] = []
        self.add_post_calls: list[tuple[str, Any]] = []
        self.raise_on_add: Exception | None = None

    def add_get(self, path: str, handler: Any, **_kwargs: Any) -> Any:
        if self.raise_on_add is not None:
            raise self.raise_on_add
        self.add_get_calls.append((path, handler))
        return SimpleNamespace(method="GET")

    def add_post(self, path: str, handler: Any, **_kwargs: Any) -> Any:
        if self.raise_on_add is not None:
            raise self.raise_on_add
        self.add_post_calls.append((path, handler))
        return SimpleNamespace(method="POST")


@pytest.fixture
def hass_with_http(hass):
    """Provide a real HA hass fixture augmented with a stub http router."""
    router = _RouterStub()
    hass.http = SimpleNamespace(app=SimpleNamespace(router=router))
    return hass


def _mock_health_first_refresh(monkeypatch) -> None:
    """Calling async_setup_entry directly leaves the entry NOT_LOADED.

    The health coordinator's first refresh requires SETUP_IN_PROGRESS and does network
    I/O, so we mock it out to keep these lifecycle tests focused on wiring.
    """
    monkeypatch.setattr(
        "custom_components.sws12500.HealthCoordinator.async_config_entry_first_refresh",
        AsyncMock(return_value=None),
    )


# --- register_path ---------------------------------------------------------


@pytest.mark.asyncio
async def test_register_path_registers_routes_and_stores_dispatcher(hass_with_http):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)

    coordinator = WeatherDataUpdateCoordinator(hass_with_http, entry)
    coordinator_health = HealthCoordinator(hass_with_http, entry)

    ok = register_path(hass_with_http, coordinator, coordinator_health, entry)
    assert ok is True

    # Router registrations: GET for legacy/wslink/health, POST for wslink + ecowitt.
    router: _RouterStub = hass_with_http.http.app.router
    assert [p for (p, _h) in router.add_get_calls] == [
        DEFAULT_URL,
        WSLINK_URL,
        HEALTH_URL,
    ]
    assert [p for (p, _h) in router.add_post_calls] == [WSLINK_URL, ECOWITT_PATH]

    # Dispatcher stored under the shared (cross-reload) hass.data[DOMAIN].
    assert DOMAIN in hass_with_http.data
    routes = hass_with_http.data[DOMAIN].get("routes")
    assert routes is not None
    assert isinstance(routes.show_enabled(), str)


@pytest.mark.asyncio
async def test_register_path_raises_config_entry_not_ready_on_router_runtime_error(
    hass_with_http,
):
    from homeassistant.exceptions import ConfigEntryNotReady

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)

    coordinator = WeatherDataUpdateCoordinator(hass_with_http, entry)
    coordinator_health = HealthCoordinator(hass_with_http, entry)

    router: _RouterStub = hass_with_http.http.app.router
    router.raise_on_add = RuntimeError("router broken")

    with pytest.raises(ConfigEntryNotReady):
        register_path(hass_with_http, coordinator, coordinator_health, entry)


@pytest.mark.asyncio
async def test_register_path_checked_hass_data_wrong_type_raises_config_entry_not_ready(
    hass_with_http,
):
    """Cover register_path branch where `checked(hass.data[DOMAIN], dict)` returns None."""
    from homeassistant.exceptions import ConfigEntryNotReady

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)

    coordinator = WeatherDataUpdateCoordinator(hass_with_http, entry)
    coordinator_health = HealthCoordinator(hass_with_http, entry)

    hass_with_http.data[DOMAIN] = []  # wrong type -> checked(..., dict) fails

    with pytest.raises(ConfigEntryNotReady):
        register_path(hass_with_http, coordinator, coordinator_health, entry)


# --- async_setup_entry -----------------------------------------------------


@pytest.mark.asyncio
async def test_async_setup_entry_creates_runtime_data_and_forwards_platforms(
    hass_with_http,
    monkeypatch,
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)

    _mock_health_first_refresh(monkeypatch)
    monkeypatch.setattr(
        hass_with_http.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=True),
    )

    ok = await async_setup_entry(hass_with_http, entry)
    assert ok is True

    # Per-entry state now lives on entry.runtime_data (SWSRuntimeData).
    assert isinstance(entry.runtime_data, SWSRuntimeData)
    assert isinstance(entry.runtime_data.coordinator, WeatherDataUpdateCoordinator)
    assert isinstance(entry.runtime_data.last_options, dict)

    # Shared dispatcher registered under hass.data[DOMAIN].
    assert "routes" in hass_with_http.data[DOMAIN]

    hass_with_http.config_entries.async_forward_entry_setups.assert_awaited()


@pytest.mark.asyncio
async def test_async_setup_entry_fatal_when_register_path_returns_false(
    hass_with_http, monkeypatch
):
    """Cover the fatal branch when `register_path` returns False -> PlatformNotReady."""
    from homeassistant.exceptions import PlatformNotReady

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)

    # No pre-registered routes -> async_setup_entry calls register_path.
    hass_with_http.data.setdefault(DOMAIN, {})
    hass_with_http.data[DOMAIN].pop("routes", None)

    monkeypatch.setattr(
        "custom_components.sws12500.register_path",
        lambda _hass, _coordinator, _coordinator_h, _entry: False,
    )
    monkeypatch.setattr(
        hass_with_http.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=True),
    )

    with pytest.raises(PlatformNotReady):
        await async_setup_entry(hass_with_http, entry)


@pytest.mark.asyncio
async def test_async_setup_entry_reuses_route_dispatcher_and_switches_protocol(
    hass_with_http,
    monkeypatch,
):
    """On reload the shared route dispatcher is reused; the coordinator is recreated."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)

    # Pre-register routes once (legacy/WU active).
    initial_coordinator = WeatherDataUpdateCoordinator(hass_with_http, entry)
    initial_health = HealthCoordinator(hass_with_http, entry)
    register_path(hass_with_http, initial_coordinator, initial_health, entry)
    routes_before = hass_with_http.data[DOMAIN]["routes"]
    assert routes_before.path_enabled(DEFAULT_URL) is True

    # Switch to WSLink and run setup again.
    hass_with_http.config_entries.async_update_entry(
        entry, options={**dict(entry.options), WSLINK: True}
    )

    _mock_health_first_refresh(monkeypatch)
    monkeypatch.setattr(
        hass_with_http.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=True),
    )

    ok = await async_setup_entry(hass_with_http, entry)
    assert ok is True

    # Same dispatcher object reused (survives across reloads).
    assert hass_with_http.data[DOMAIN]["routes"] is routes_before
    # Protocol switched to WSLink.
    assert routes_before.path_enabled(WSLINK_URL) is True
    assert routes_before.path_enabled(DEFAULT_URL) is False
    # A fresh coordinator is wired onto entry.runtime_data.
    assert isinstance(entry.runtime_data, SWSRuntimeData)
    assert isinstance(entry.runtime_data.coordinator, WeatherDataUpdateCoordinator)


# --- update_listener -------------------------------------------------------


def _entry_with_runtime(hass, *, options: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options)
    entry.add_to_hass(hass)
    entry.runtime_data = SWSRuntimeData(
        coordinator=object(),  # type: ignore[arg-type]
        health_coordinator=object(),  # type: ignore[arg-type]
        last_options=dict(options),
    )
    return entry


@pytest.mark.asyncio
async def test_update_listener_skips_reload_when_only_sensors_to_load_changes(
    hass_with_http,
):
    entry = _entry_with_runtime(
        hass_with_http,
        options={API_ID: "id", API_KEY: "key", SENSORS_TO_LOAD: ["a"]},
    )

    hass_with_http.config_entries.async_reload = AsyncMock()

    # Only SENSORS_TO_LOAD changes.
    hass_with_http.config_entries.async_update_entry(
        entry, options={**dict(entry.options), SENSORS_TO_LOAD: ["a", "b"]}
    )

    await update_listener(hass_with_http, entry)

    hass_with_http.config_entries.async_reload.assert_not_awaited()
    # The snapshot on runtime_data is refreshed.
    assert entry.runtime_data.last_options == dict(entry.options)


@pytest.mark.asyncio
async def test_update_listener_triggers_reload_when_other_option_changes(
    hass_with_http,
    monkeypatch,
):
    entry = _entry_with_runtime(
        hass_with_http,
        options={API_ID: "id", API_KEY: "key", SENSORS_TO_LOAD: ["a"], WSLINK: False},
    )

    hass_with_http.config_entries.async_reload = AsyncMock(return_value=True)

    hass_with_http.config_entries.async_update_entry(
        entry, options={**dict(entry.options), WSLINK: True}
    )

    info = MagicMock()
    monkeypatch.setattr("custom_components.sws12500._LOGGER.info", info)

    await update_listener(hass_with_http, entry)

    hass_with_http.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
    info.assert_called()


@pytest.mark.asyncio
async def test_update_listener_without_runtime_snapshot_reloads(hass_with_http):
    """When runtime_data is not a valid snapshot, update_listener reloads."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", SENSORS_TO_LOAD: ["a"], WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)
    # Not an SWSRuntimeData instance -> the skip-reload fast path is bypassed.
    entry.runtime_data = "invalid"

    hass_with_http.config_entries.async_reload = AsyncMock(return_value=True)

    await update_listener(hass_with_http, entry)

    hass_with_http.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)


# --- async_unload_entry ----------------------------------------------------


@pytest.mark.asyncio
async def test_async_unload_entry_returns_true_on_success(hass_with_http):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={API_ID: "id", API_KEY: "key"})
    entry.add_to_hass(hass_with_http)

    hass_with_http.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    ok = await async_unload_entry(hass_with_http, entry)

    assert ok is True
    hass_with_http.config_entries.async_unload_platforms.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_unload_entry_returns_false_on_failure(hass_with_http):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={API_ID: "id", API_KEY: "key"})
    entry.add_to_hass(hass_with_http)

    hass_with_http.config_entries.async_unload_platforms = AsyncMock(return_value=False)

    ok = await async_unload_entry(hass_with_http, entry)

    assert ok is False


# --- coordinator auth (lifecycle-adjacent) ---------------------------------


@pytest.mark.asyncio
async def test_received_data_auth_unauthorized_and_incorrect_data_paths(hass):
    """Cover coordinator auth behavior reachable from the webhook entrypoint."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", WSLINK: False},
    )
    entry.add_to_hass(hass)
    entry.runtime_data = SWSRuntimeData(coordinator=object(), health_coordinator=None, last_options={})  # type: ignore[arg-type]
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    # Missing security params -> unauthorized
    with pytest.raises(HTTPUnauthorized):
        await coordinator.received_data(_RequestStub(query={"x": "y"}))  # type: ignore[arg-type]

    # Wrong credentials -> unauthorized
    with pytest.raises(HTTPUnauthorized):
        await coordinator.received_data(
            _RequestStub(query={"ID": "id", "PASSWORD": "no"})
        )  # type: ignore[arg-type]

    # Missing API_ID in options -> IncorrectDataError
    entry2 = MockConfigEntry(domain=DOMAIN, data={}, options={API_KEY: "key", WSLINK: False})
    entry2.add_to_hass(hass)
    entry2.runtime_data = SWSRuntimeData(coordinator=object(), health_coordinator=None, last_options={})  # type: ignore[arg-type]
    coordinator2 = WeatherDataUpdateCoordinator(hass, entry2)
    with pytest.raises(IncorrectDataError):
        await coordinator2.received_data(
            _RequestStub(query={"ID": "id", "PASSWORD": "key"})
        )  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_received_data_returns_503_when_runtime_data_missing(hass):
    """A payload arriving while the entry is unloaded is rejected with 503, not 500."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={API_ID: "id", API_KEY: "key", WSLINK: False})
    entry.add_to_hass(hass)
    # No runtime_data assigned -> simulates the unloaded/reloading window.
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    resp = await coordinator.received_data(
        _RequestStub(query={"ID": "id", "PASSWORD": "key"})
    )  # type: ignore[arg-type]
    assert resp.status == 503


@pytest.mark.asyncio
async def test_register_path_idempotent_when_routes_exist(hass_with_http):
    """A second register_path call reuses the existing dispatcher (no new aiohttp routes)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)

    coordinator = WeatherDataUpdateCoordinator(hass_with_http, entry)
    coordinator_health = HealthCoordinator(hass_with_http, entry)

    assert register_path(hass_with_http, coordinator, coordinator_health, entry) is True
    router: _RouterStub = hass_with_http.http.app.router
    get_calls_after_first = list(router.add_get_calls)
    post_calls_after_first = list(router.add_post_calls)

    # Routes already a Routes instance -> else branch; nothing re-registered on aiohttp.
    assert register_path(hass_with_http, coordinator, coordinator_health, entry) is True
    assert router.add_get_calls == get_calls_after_first
    assert router.add_post_calls == post_calls_after_first
