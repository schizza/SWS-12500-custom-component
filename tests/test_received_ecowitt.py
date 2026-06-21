from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiohttp.web_exceptions import HTTPUnauthorized
import pytest

from custom_components.sws12500.const import (
    API_ID,
    API_KEY,
    DEV_DBG,
    ECOWITT_ENABLED,
    ECOWITT_WEBHOOK_ID,
    POCASI_CZ_ENABLED,
    SENSORS_TO_LOAD,
    WINDY_ENABLED,
    WSLINK,
)
from custom_components.sws12500.coordinator import WeatherDataUpdateCoordinator
from homeassistant.util import dt as dt_util


@dataclass(slots=True)
class _EcowittRequestStub:
    """Minimal aiohttp Request stub for the Ecowitt endpoint.

    The coordinator uses `webdata.match_info.get("webhook_id", "")` and
    `await webdata.post()`.
    """

    match_info: dict[str, Any] = field(default_factory=dict)
    post_data: dict[str, Any] | None = None

    async def post(self) -> dict[str, Any]:
        return self.post_data or {}


@dataclass(slots=True)
class _RequestStub:
    """Minimal aiohttp Request stub for the legacy endpoint.

    The coordinator uses `webdata.query` and `await webdata.post()`.
    """

    query: dict[str, Any]
    post_data: dict[str, Any] | None = None

    async def post(self) -> dict[str, Any]:
        return self.post_data or {}


def _make_entry(
    *,
    wslink: bool = False,
    api_id: str | None = "id",
    api_key: str | None = "key",
    windy_enabled: bool = False,
    pocasi_enabled: bool = False,
    dev_debug: bool = False,
    ecowitt_enabled: bool = False,
    ecowitt_webhook_id: str | None = None,
    health: Any = None,
) -> Any:
    """Create a minimal config entry stub with `.options` and `.entry_id`."""
    options: dict[str, Any] = {
        WSLINK: wslink,
        WINDY_ENABLED: windy_enabled,
        POCASI_CZ_ENABLED: pocasi_enabled,
        ECOWITT_ENABLED: ecowitt_enabled,
        DEV_DBG: dev_debug,
    }
    if api_id is not None:
        options[API_ID] = api_id
    if api_key is not None:
        options[API_KEY] = api_key
    if ecowitt_webhook_id is not None:
        options[ECOWITT_WEBHOOK_ID] = ecowitt_webhook_id

    entry = SimpleNamespace()
    entry.entry_id = "test_entry_id"
    entry.options = options
    # DataUpdateCoordinator.__init__ calls config_entry.async_on_unload(...) when a
    # config_entry is passed (see WeatherDataUpdateCoordinator.__init__).
    entry.async_on_unload = lambda *_args, **_kwargs: None
    # Per-entry runtime state lives on entry.runtime_data (SWSRuntimeData) since v2.0.
    entry.runtime_data = SimpleNamespace(
        health_coordinator=health,
        add_sensor_entities=None,
        add_binary_entities=None,
        last_seen={},
        started_at=dt_util.utcnow(),
    )
    return entry


def _make_health_stub() -> Any:
    """Create a MagicMock-based stub for the HealthCoordinator branches."""
    return SimpleNamespace(
        update_ingress_result=MagicMock(),
        update_forwarding=MagicMock(),
    )


# ---------------------------------------------------------------------------
# received_ecowitt_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_received_ecowitt_disabled_returns_403_and_reports_health(hass, monkeypatch):
    """Branch 1: Ecowitt disabled -> 403 and health.update_ingress_result(disabled)."""
    health = _make_health_stub()
    entry = _make_entry(ecowitt_enabled=False, health=health)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    request = _EcowittRequestStub(match_info={"webhook_id": "abc"})
    resp = await coordinator.received_ecowitt_data(request)  # type: ignore[arg-type]

    assert resp.status == 403
    assert resp.text == "Ecowitt disabled"
    health.update_ingress_result.assert_called_once()
    _args, kwargs = health.update_ingress_result.call_args
    assert kwargs["accepted"] is False
    assert kwargs["authorized"] is None
    assert kwargs["reason"] == "ecowitt_disabled"


@pytest.mark.asyncio
async def test_received_ecowitt_disabled_no_health(hass, monkeypatch):
    """Branch 1 without health: covers the `if health` False edge for disabled."""
    entry = _make_entry(ecowitt_enabled=False, health=None)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    request = _EcowittRequestStub(match_info={"webhook_id": "abc"})
    resp = await coordinator.received_ecowitt_data(request)  # type: ignore[arg-type]

    assert resp.status == 403


@pytest.mark.asyncio
async def test_received_ecowitt_missing_webhook_id_raises_unauthorized(hass, monkeypatch):
    """Branch 2: enabled but expected webhook id missing -> HTTPUnauthorized."""
    health = _make_health_stub()
    entry = _make_entry(
        ecowitt_enabled=True, ecowitt_webhook_id=None, health=health
    )
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    request = _EcowittRequestStub(match_info={"webhook_id": "abc"})
    with pytest.raises(HTTPUnauthorized):
        await coordinator.received_ecowitt_data(request)  # type: ignore[arg-type]

    health.update_ingress_result.assert_called_once()
    _args, kwargs = health.update_ingress_result.call_args
    assert kwargs["accepted"] is False
    assert kwargs["authorized"] is False
    assert kwargs["reason"] == "ecowitt_invalid_webhook_id"


@pytest.mark.asyncio
async def test_received_ecowitt_mismatched_webhook_id_raises_unauthorized(hass, monkeypatch):
    """Branch 2: enabled but webhook id mismatch -> HTTPUnauthorized (no health)."""
    entry = _make_entry(
        ecowitt_enabled=True, ecowitt_webhook_id="expected", health=None
    )
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    request = _EcowittRequestStub(match_info={"webhook_id": "wrong"})
    with pytest.raises(HTTPUnauthorized):
        await coordinator.received_ecowitt_data(request)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_received_ecowitt_success_full_pipeline_with_health_autodiscovery_forwarding_devlog(
    hass, monkeypatch
):
    """Branch 3 success: covers lines 132-172.

    - process_payload returns a mapped dict
    - check_disabled returns new keys -> autodiscovery (update_options,
      add_new_binary_sensors, add_new_sensors)
    - async_set_updated_data + last_seen + update_stale_sensors_issue
    - health.update_ingress_result(accepted) + windy + pocasi forwarding
    - health.update_forwarding
    - dev log via anonymize
    """
    health = _make_health_stub()
    entry = _make_entry(
        ecowitt_enabled=True,
        ecowitt_webhook_id="hook",
        windy_enabled=True,
        pocasi_enabled=True,
        dev_debug=True,
        health=health,
    )
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    mapped = {"outside_temp": "20"}
    coordinator.ecowitt_bridge.process_payload = AsyncMock(return_value=mapped)

    # Autodiscovery: one new sensor key.
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _mapped, _config: ["outside_temp"],
    )
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.loaded_sensors", lambda _c: []
    )

    update_options = AsyncMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.update_options", update_options
    )
    add_new_sensors = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.add_new_sensors", add_new_sensors
    )
    add_new_binary_sensors = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.add_new_binary_sensors",
        add_new_binary_sensors,
    )
    update_stale = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.update_stale_sensors_issue",
        update_stale,
    )

    coordinator.windy.push_data_to_windy = AsyncMock()
    coordinator.pocasi.push_data_to_server = AsyncMock()

    anonymize = MagicMock(return_value={"safe": True})
    monkeypatch.setattr("custom_components.sws12500.coordinator.anonymize", anonymize)
    log_info = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.coordinator._LOGGER.info", log_info)

    coordinator.async_set_updated_data = MagicMock()

    request = _EcowittRequestStub(
        match_info={"webhook_id": "hook"}, post_data={"tempf": "68"}
    )
    resp = await coordinator.received_ecowitt_data(request)  # type: ignore[arg-type]

    assert resp.status == 200

    coordinator.ecowitt_bridge.process_payload.assert_awaited_once()

    # Autodiscovery side-effects.
    update_options.assert_awaited_once()
    args, _kwargs = update_options.await_args
    assert args[2] == SENSORS_TO_LOAD
    assert "outside_temp" in args[3]
    add_new_sensors.assert_called_once_with(hass, entry, ["outside_temp"])
    add_new_binary_sensors.assert_called_once_with(hass, entry, ["outside_temp"])

    # Coordinator data + staleness + last_seen.
    coordinator.async_set_updated_data.assert_called_once_with(mapped)
    update_stale.assert_called_once()
    assert "outside_temp" in entry.runtime_data.last_seen

    # Forwarding: windy receives the raw data dict + False, pocasi receives "WU".
    coordinator.windy.push_data_to_windy.assert_awaited_once()
    w_args, _ = coordinator.windy.push_data_to_windy.await_args
    assert isinstance(w_args[0], dict)
    assert w_args[1] is False
    coordinator.pocasi.push_data_to_server.assert_awaited_once()
    p_args, _ = coordinator.pocasi.push_data_to_server.await_args
    assert p_args[1] == "WU"

    # Health branches.
    health.update_ingress_result.assert_called_once()
    _ia, ikw = health.update_ingress_result.call_args
    assert ikw["accepted"] is True
    assert ikw["authorized"] is True
    assert ikw["reason"] == "accepted"
    health.update_forwarding.assert_called_once_with(coordinator.windy, coordinator.pocasi)

    # Dev log.
    anonymize.assert_called_once()
    log_info.assert_called_once()


@pytest.mark.asyncio
async def test_received_ecowitt_success_no_health_no_autodiscovery_no_forwarding(
    hass, monkeypatch
):
    """Branch 3 success with all optional branches False.

    - health is None (skips both `if health` blocks)
    - check_disabled returns [] (skips autodiscovery body)
    - windy/pocasi disabled (skips forwarding)
    - dev debug off (skips dev log)
    """
    entry = _make_entry(
        ecowitt_enabled=True,
        ecowitt_webhook_id="hook",
        windy_enabled=False,
        pocasi_enabled=False,
        dev_debug=False,
        health=None,
    )
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    mapped = {"outside_temp": "20"}
    coordinator.ecowitt_bridge.process_payload = AsyncMock(return_value=mapped)

    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _mapped, _config: [],
    )
    update_stale = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.update_stale_sensors_issue",
        update_stale,
    )

    coordinator.windy.push_data_to_windy = AsyncMock()
    coordinator.pocasi.push_data_to_server = AsyncMock()
    coordinator.async_set_updated_data = MagicMock()

    request = _EcowittRequestStub(match_info={"webhook_id": "hook"})
    resp = await coordinator.received_ecowitt_data(request)  # type: ignore[arg-type]

    assert resp.status == 200
    coordinator.async_set_updated_data.assert_called_once_with(mapped)
    update_stale.assert_called_once()
    coordinator.windy.push_data_to_windy.assert_not_awaited()
    coordinator.pocasi.push_data_to_server.assert_not_awaited()


@pytest.mark.asyncio
async def test_received_ecowitt_autodiscovery_extends_with_loaded_sensors(hass, monkeypatch):
    """Line 138: cover the `_loaded_sensors := loaded_sensors(...)` extend branch."""
    entry = _make_entry(ecowitt_enabled=True, ecowitt_webhook_id="hook", health=None)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    mapped = {"new": "1"}
    coordinator.ecowitt_bridge.process_payload = AsyncMock(return_value=mapped)

    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _mapped, _config: ["new"],
    )
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.loaded_sensors", lambda _c: ["existing"]
    )

    update_options = AsyncMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.update_options", update_options
    )
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.add_new_sensors", MagicMock()
    )
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.add_new_binary_sensors", MagicMock()
    )
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.update_stale_sensors_issue", MagicMock()
    )
    coordinator.async_set_updated_data = MagicMock()

    request = _EcowittRequestStub(match_info={"webhook_id": "hook"})
    resp = await coordinator.received_ecowitt_data(request)  # type: ignore[arg-type]

    assert resp.status == 200
    update_options.assert_awaited_once()
    args, _kwargs = update_options.await_args
    assert args[2] == SENSORS_TO_LOAD
    assert set(args[3]) >= {"new", "existing"}


@pytest.mark.asyncio
async def test_health_coordinator_attribute_error_returns_none(hass, monkeypatch):
    """Lines 92-93: runtime_data without health_coordinator -> AttributeError -> None."""
    entry = _make_entry(ecowitt_enabled=True, ecowitt_webhook_id="hook")
    # Replace runtime_data with one that lacks `health_coordinator`.
    entry.runtime_data = SimpleNamespace(last_seen={})
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    assert coordinator._health_coordinator() is None

    mapped = {"outside_temp": "20"}
    coordinator.ecowitt_bridge.process_payload = AsyncMock(return_value=mapped)
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _mapped, _config: [],
    )
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.update_stale_sensors_issue", MagicMock()
    )
    coordinator.async_set_updated_data = MagicMock()

    request = _EcowittRequestStub(match_info={"webhook_id": "hook"})
    resp = await coordinator.received_ecowitt_data(request)  # type: ignore[arg-type]
    assert resp.status == 200


@pytest.mark.asyncio
async def test_received_ecowitt_empty_mapped_skips_update_block(hass, monkeypatch):
    """Branch 3 success but process_payload returns empty -> skips the `if mapped_data` block."""
    entry = _make_entry(ecowitt_enabled=True, ecowitt_webhook_id="hook", health=None)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    coordinator.ecowitt_bridge.process_payload = AsyncMock(return_value={})

    update_stale = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.update_stale_sensors_issue",
        update_stale,
    )
    coordinator.async_set_updated_data = MagicMock()

    request = _EcowittRequestStub(match_info={"webhook_id": "hook"})
    resp = await coordinator.received_ecowitt_data(request)  # type: ignore[arg-type]

    assert resp.status == 200
    coordinator.async_set_updated_data.assert_not_called()
    update_stale.assert_not_called()


# ---------------------------------------------------------------------------
# received_data health branches (lines 196, 207, 225, 236, 252, 304, 321)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_received_data_wu_missing_credentials_reports_health(hass, monkeypatch):
    """Line 196: WU missing credentials -> health.update_ingress_result."""
    health = _make_health_stub()
    entry = _make_entry(wslink=False, health=health)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    with pytest.raises(HTTPUnauthorized):
        await coordinator.received_data(_RequestStub(query={"foo": "bar"}))  # type: ignore[arg-type]

    health.update_ingress_result.assert_called_once()
    _a, kw = health.update_ingress_result.call_args
    assert kw["reason"] == "missing_credentials"
    assert kw["accepted"] is False
    assert kw["authorized"] is False


@pytest.mark.asyncio
async def test_received_data_wslink_missing_credentials_reports_health(hass, monkeypatch):
    """Line 207: WSLink missing credentials -> health.update_ingress_result."""
    health = _make_health_stub()
    entry = _make_entry(wslink=True, health=health)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    with pytest.raises(HTTPUnauthorized):
        await coordinator.received_data(_RequestStub(query={"foo": "bar"}))  # type: ignore[arg-type]

    health.update_ingress_result.assert_called_once()
    _a, kw = health.update_ingress_result.call_args
    assert kw["reason"] == "missing_credentials"


@pytest.mark.asyncio
async def test_received_data_missing_api_id_reports_health(hass, monkeypatch):
    """Line 225: missing API ID -> health.update_ingress_result(config_missing_api_id)."""
    from custom_components.sws12500.coordinator import IncorrectDataError

    health = _make_health_stub()
    entry = _make_entry(wslink=False, api_id=None, api_key="key", health=health)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    with pytest.raises(IncorrectDataError):
        await coordinator.received_data(
            _RequestStub(query={"ID": "id", "PASSWORD": "key"})
        )  # type: ignore[arg-type]

    health.update_ingress_result.assert_called_once()
    _a, kw = health.update_ingress_result.call_args
    assert kw["reason"] == "config_missing_api_id"
    assert kw["authorized"] is None


@pytest.mark.asyncio
async def test_received_data_missing_api_key_reports_health(hass, monkeypatch):
    """Line 236: missing API KEY -> health.update_ingress_result(config_missing_api_key)."""
    from custom_components.sws12500.coordinator import IncorrectDataError

    health = _make_health_stub()
    entry = _make_entry(wslink=False, api_id="id", api_key=None, health=health)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    with pytest.raises(IncorrectDataError):
        await coordinator.received_data(
            _RequestStub(query={"ID": "id", "PASSWORD": "key"})
        )  # type: ignore[arg-type]

    health.update_ingress_result.assert_called_once()
    _a, kw = health.update_ingress_result.call_args
    assert kw["reason"] == "config_missing_api_key"


@pytest.mark.asyncio
async def test_received_data_wrong_credentials_reports_health(hass, monkeypatch):
    """Line 252: wrong credentials -> health.update_ingress_result(unauthorized)."""
    health = _make_health_stub()
    entry = _make_entry(wslink=False, api_id="id", api_key="key", health=health)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    with pytest.raises(HTTPUnauthorized):
        await coordinator.received_data(
            _RequestStub(query={"ID": "id", "PASSWORD": "wrong"})
        )  # type: ignore[arg-type]

    health.update_ingress_result.assert_called_once()
    _a, kw = health.update_ingress_result.call_args
    assert kw["reason"] == "unauthorized"
    assert kw["authorized"] is False


@pytest.mark.asyncio
async def test_received_data_success_with_health_autodiscovery_and_binary(hass, monkeypatch):
    """Lines 304 + 321: success path with health stub and autodiscovery.

    - check_disabled returns a key -> add_new_binary_sensors (line 294/304-region)
    - health accepted branch (line 304) + health.update_forwarding (line 321)
    """
    health = _make_health_stub()
    entry = _make_entry(wslink=False, api_id="id", api_key="key", health=health)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    remapped = {"x": "1"}
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.remap_items", lambda _d: remapped
    )
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _r, _c: ["x"],
    )
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.loaded_sensors", lambda _c: []
    )

    async def _translations(_hass, _domain, _key, **_kwargs):
        return "Name"

    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.translations", _translations
    )
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.translated_notification", AsyncMock()
    )
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.update_options", AsyncMock()
    )
    add_new_sensors = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.add_new_sensors", add_new_sensors
    )
    add_new_binary_sensors = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.add_new_binary_sensors",
        add_new_binary_sensors,
    )

    coordinator.async_set_updated_data = MagicMock()

    resp = await coordinator.received_data(
        _RequestStub(query={"ID": "id", "PASSWORD": "key"})
    )  # type: ignore[arg-type]

    assert resp.status == 200
    add_new_binary_sensors.assert_called_once()

    # Health accepted (line 304) and forwarding (line 321).
    assert health.update_ingress_result.call_count == 1
    _a, kw = health.update_ingress_result.call_args
    assert kw["accepted"] is True
    assert kw["reason"] == "accepted"
    health.update_forwarding.assert_called_once_with(coordinator.windy, coordinator.pocasi)
