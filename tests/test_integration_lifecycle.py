from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiohttp.web_exceptions import HTTPUnauthorized
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sws12500 import (
    HealthCoordinator,
    IncorrectDataError,
    WeatherDataUpdateCoordinator,
    async_setup_entry,
    async_unload_entry,
    register_path,
    update_listener,
)
from custom_components.sws12500.const import (
    API_ID,
    API_KEY,
    DEFAULT_URL,
    DOMAIN,
    HEALTH_URL,
    SENSORS_TO_LOAD,
    WSLINK,
    WSLINK_URL,
)
from custom_components.sws12500.data import ENTRY_COORDINATOR, ENTRY_LAST_OPTIONS


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


@pytest.mark.asyncio
async def test_register_path_registers_routes_and_stores_dispatcher(hass_with_http):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            API_ID: "id",
            API_KEY: "key",
            WSLINK: False,
        },
    )
    entry.add_to_hass(hass_with_http)

    coordinator = WeatherDataUpdateCoordinator(hass_with_http, entry)
    coordinator_health = HealthCoordinator(hass_with_http, entry)

    ok = register_path(hass_with_http, coordinator, coordinator_health, entry)
    assert ok is True

    # Router registrations
    router: _RouterStub = hass_with_http.http.app.router
    assert [p for (p, _h) in router.add_get_calls] == [
        DEFAULT_URL,
        WSLINK_URL,
        HEALTH_URL,
    ]
    assert [p for (p, _h) in router.add_post_calls] == [WSLINK_URL]

    # Dispatcher stored
    assert DOMAIN in hass_with_http.data
    assert "routes" in hass_with_http.data[DOMAIN]
    routes = hass_with_http.data[DOMAIN]["routes"]
    assert routes is not None
    # show_enabled() should return a string
    assert isinstance(routes.show_enabled(), str)


@pytest.mark.asyncio
async def test_register_path_raises_config_entry_not_ready_on_router_runtime_error(
    hass_with_http,
):
    from homeassistant.exceptions import ConfigEntryNotReady

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            API_ID: "id",
            API_KEY: "key",
            WSLINK: False,
        },
    )
    entry.add_to_hass(hass_with_http)

    coordinator = WeatherDataUpdateCoordinator(hass_with_http, entry)
    coordinator_health = HealthCoordinator(hass_with_http, entry)

    # Make router raise RuntimeError on add
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
        options={
            API_ID: "id",
            API_KEY: "key",
            WSLINK: False,
        },
    )
    entry.add_to_hass(hass_with_http)

    coordinator = WeatherDataUpdateCoordinator(hass_with_http, entry)
    coordinator_health = HealthCoordinator(hass_with_http, entry)

    # Force wrong type under DOMAIN so `checked(..., dict)` fails.
    hass_with_http.data[DOMAIN] = []

    with pytest.raises(ConfigEntryNotReady):
        register_path(hass_with_http, coordinator, coordinator_health, entry)


@pytest.mark.asyncio
async def test_async_setup_entry_creates_entry_dict_and_coordinator_and_forwards_platforms(
    hass_with_http,
    monkeypatch,
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)

    # Avoid loading actual platforms via HA loader.
    monkeypatch.setattr(
        hass_with_http.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=True),
    )

    ok = await async_setup_entry(hass_with_http, entry)
    assert ok is True

    # Runtime storage exists and is a dict
    assert DOMAIN in hass_with_http.data
    assert entry.entry_id in hass_with_http.data[DOMAIN]
    entry_data = hass_with_http.data[DOMAIN][entry.entry_id]
    assert isinstance(entry_data, dict)

    # Coordinator stored and last options snapshot stored
    assert isinstance(entry_data.get(ENTRY_COORDINATOR), WeatherDataUpdateCoordinator)
    assert isinstance(entry_data.get(ENTRY_LAST_OPTIONS), dict)

    # Forwarded setups invoked
    hass_with_http.config_entries.async_forward_entry_setups.assert_awaited()


@pytest.mark.asyncio
async def test_async_setup_entry_fatal_when_register_path_returns_false(
    hass_with_http, monkeypatch
):
    """Cover the fatal branch when `register_path` returns False.

    async_setup_entry does:
      routes_enabled = register_path(...)
      if not routes_enabled: raise PlatformNotReady
    """
    from homeassistant.exceptions import PlatformNotReady

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)

    # Ensure there are no pre-registered routes so async_setup_entry calls register_path.
    hass_with_http.data.setdefault(DOMAIN, {})
    hass_with_http.data[DOMAIN].pop("routes", None)

    # Force register_path to return False
    monkeypatch.setattr(
        "custom_components.sws12500.register_path",
        lambda _hass, _coordinator, _coordinator_h, _entry: False,
    )

    # Forwarding shouldn't be reached; patch anyway to avoid accidental loader calls.
    monkeypatch.setattr(
        hass_with_http.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=True),
    )

    with pytest.raises(PlatformNotReady):
        await async_setup_entry(hass_with_http, entry)


@pytest.mark.asyncio
async def test_async_setup_entry_reuses_existing_coordinator_and_switches_routes(
    hass_with_http,
    monkeypatch,
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)

    # Pretend setup already happened and a coordinator exists
    hass_with_http.data.setdefault(DOMAIN, {})
    existing_coordinator = WeatherDataUpdateCoordinator(hass_with_http, entry)
    hass_with_http.data[DOMAIN][entry.entry_id] = {
        ENTRY_COORDINATOR: existing_coordinator,
        ENTRY_LAST_OPTIONS: dict(entry.options),
    }

    # Provide pre-registered routes dispatcher
    routes = hass_with_http.data[DOMAIN].get("routes")
    if routes is None:
        # Create a dispatcher via register_path once
        coordinator_health = HealthCoordinator(hass_with_http, entry)
        register_path(hass_with_http, existing_coordinator, coordinator_health, entry)
        routes = hass_with_http.data[DOMAIN]["routes"]

    # Turn on WSLINK to trigger dispatcher switching.
    # ConfigEntry.options cannot be changed directly; use async_update_entry.
    hass_with_http.config_entries.async_update_entry(
        entry, options={**dict(entry.options), WSLINK: True}
    )

    # Avoid loading actual platforms via HA loader.
    monkeypatch.setattr(
        hass_with_http.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=True),
    )

    ok = await async_setup_entry(hass_with_http, entry)
    assert ok is True

    # Coordinator reused (same object)
    entry_data = hass_with_http.data[DOMAIN][entry.entry_id]
    assert entry_data[ENTRY_COORDINATOR] is existing_coordinator


@pytest.mark.asyncio
async def test_update_listener_skips_reload_when_only_sensors_to_load_changes(
    hass_with_http,
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", SENSORS_TO_LOAD: ["a"]},
    )
    entry.add_to_hass(hass_with_http)

    # Seed hass.data snapshot
    hass_with_http.data.setdefault(DOMAIN, {})
    hass_with_http.data[DOMAIN][entry.entry_id] = {
        # Seed the full old options snapshot. If we only store SENSORS_TO_LOAD here,
        # update_listener will detect differences for other keys (e.g. auth keys) and reload.
        ENTRY_LAST_OPTIONS: dict(entry.options),
    }

    hass_with_http.config_entries.async_reload = AsyncMock()

    # Only SENSORS_TO_LOAD changes.
    # ConfigEntry.options cannot be changed directly; use async_update_entry.
    hass_with_http.config_entries.async_update_entry(
        entry, options={**dict(entry.options), SENSORS_TO_LOAD: ["a", "b"]}
    )

    await update_listener(hass_with_http, entry)

    hass_with_http.config_entries.async_reload.assert_not_awaited()
    # Snapshot should be updated
    entry_data = hass_with_http.data[DOMAIN][entry.entry_id]
    assert entry_data[ENTRY_LAST_OPTIONS] == dict(entry.options)


@pytest.mark.asyncio
async def test_update_listener_triggers_reload_when_other_option_changes(
    hass_with_http,
    monkeypatch,
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", SENSORS_TO_LOAD: ["a"], WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)

    hass_with_http.data.setdefault(DOMAIN, {})
    hass_with_http.data[DOMAIN][entry.entry_id] = {
        ENTRY_LAST_OPTIONS: dict(entry.options),
    }

    hass_with_http.config_entries.async_reload = AsyncMock(return_value=True)

    # Change a different option.
    # ConfigEntry.options cannot be changed directly; use async_update_entry.
    hass_with_http.config_entries.async_update_entry(
        entry, options={**dict(entry.options), WSLINK: True}
    )

    info = MagicMock()
    monkeypatch.setattr("custom_components.sws12500._LOGGER.info", info)

    await update_listener(hass_with_http, entry)

    hass_with_http.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
    info.assert_called()


@pytest.mark.asyncio
async def test_update_listener_missing_snapshot_stores_current_options_then_reloads(
    hass_with_http,
):
    """Cover update_listener branch where the options snapshot is missing/invalid.

    This hits:
        entry_data[ENTRY_LAST_OPTIONS] = dict(entry.options)
    and then proceeds to reload.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", SENSORS_TO_LOAD: ["a"], WSLINK: False},
    )
    entry.add_to_hass(hass_with_http)

    hass_with_http.data.setdefault(DOMAIN, {})
    # Store an invalid snapshot type to force the "No/invalid snapshot" branch.
    hass_with_http.data[DOMAIN][entry.entry_id] = {ENTRY_LAST_OPTIONS: "invalid"}

    hass_with_http.config_entries.async_reload = AsyncMock(return_value=True)

    await update_listener(hass_with_http, entry)

    entry_data = hass_with_http.data[DOMAIN][entry.entry_id]
    assert entry_data[ENTRY_LAST_OPTIONS] == dict(entry.options)
    hass_with_http.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_async_unload_entry_pops_runtime_data_on_success(hass_with_http):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key"},
    )
    entry.add_to_hass(hass_with_http)

    hass_with_http.data.setdefault(DOMAIN, {})
    hass_with_http.data[DOMAIN][entry.entry_id] = {ENTRY_COORDINATOR: object()}

    hass_with_http.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    ok = await async_unload_entry(hass_with_http, entry)
    assert ok is True
    assert entry.entry_id not in hass_with_http.data[DOMAIN]


@pytest.mark.asyncio
async def test_async_unload_entry_keeps_runtime_data_on_failure(hass_with_http):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key"},
    )
    entry.add_to_hass(hass_with_http)

    hass_with_http.data.setdefault(DOMAIN, {})
    hass_with_http.data[DOMAIN][entry.entry_id] = {ENTRY_COORDINATOR: object()}

    hass_with_http.config_entries.async_unload_platforms = AsyncMock(return_value=False)

    ok = await async_unload_entry(hass_with_http, entry)
    assert ok is False
    assert entry.entry_id in hass_with_http.data[DOMAIN]


@pytest.mark.asyncio
async def test_received_data_auth_unauthorized_and_incorrect_data_paths(hass):
    """A few lifecycle-adjacent assertions to cover coordinator auth behavior in __init__.py."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={API_ID: "id", API_KEY: "key", WSLINK: False},
    )
    entry.add_to_hass(hass)
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
    entry2 = MockConfigEntry(
        domain=DOMAIN, data={}, options={API_KEY: "key", WSLINK: False}
    )
    entry2.add_to_hass(hass)
    coordinator2 = WeatherDataUpdateCoordinator(hass, entry2)
    with pytest.raises(IncorrectDataError):
        await coordinator2.received_data(
            _RequestStub(query={"ID": "id", "PASSWORD": "key"})
        )  # type: ignore[arg-type]
