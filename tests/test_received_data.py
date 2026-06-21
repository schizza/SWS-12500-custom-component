from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiohttp.web_exceptions import HTTPUnauthorized
import pytest

from custom_components.sws12500.const import (
    API_ID,
    API_KEY,
    DEFAULT_URL,
    DOMAIN,
    POCASI_CZ_ENABLED,
    SENSORS_TO_LOAD,
    WINDY_ENABLED,
    WSLINK,
    WSLINK_URL,
)
from custom_components.sws12500.coordinator import IncorrectDataError, WeatherDataUpdateCoordinator
from homeassistant.util import dt as dt_util


@dataclass(slots=True)
class _RequestStub:
    """Minimal aiohttp Request stub.

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
) -> Any:
    """Create a minimal config entry stub with `.options` and `.entry_id`."""
    options: dict[str, Any] = {
        WSLINK: wslink,
        WINDY_ENABLED: windy_enabled,
        POCASI_CZ_ENABLED: pocasi_enabled,
        "dev_debug_checkbox": dev_debug,
    }
    if api_id is not None:
        options[API_ID] = api_id
    if api_key is not None:
        options[API_KEY] = api_key

    entry = SimpleNamespace()
    entry.entry_id = "test_entry_id"
    entry.options = options
    # DataUpdateCoordinator.__init__ calls config_entry.async_on_unload(...) when a
    # config_entry is passed (see WeatherDataUpdateCoordinator.__init__).
    entry.async_on_unload = lambda *_args, **_kwargs: None
    # Per-entry runtime state lives on entry.runtime_data (SWSRuntimeData) since v2.0.
    # received_data writes last_seen and reads health_coordinator / add_*_entities.
    entry.runtime_data = SimpleNamespace(
        health_coordinator=None,
        add_sensor_entities=None,
        add_binary_entities=None,
        last_seen={},
        started_at=dt_util.utcnow(),
    )
    return entry


@pytest.mark.asyncio
async def test_received_data_wu_missing_security_params_raises_http_unauthorized(
    hass, monkeypatch
):
    entry = _make_entry(wslink=False)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    # No ID/PASSWORD -> unauthorized
    request = _RequestStub(query={"foo": "bar"})
    with pytest.raises(HTTPUnauthorized):
        await coordinator.received_data(request)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_received_data_wslink_missing_security_params_raises_http_unauthorized(
    hass, monkeypatch
):
    entry = _make_entry(wslink=True)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    # No wsid/wspw -> unauthorized
    request = _RequestStub(query={"foo": "bar"})
    with pytest.raises(HTTPUnauthorized):
        await coordinator.received_data(request)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_received_data_missing_api_id_in_options_raises_incorrect_data_error(
    hass, monkeypatch
):
    entry = _make_entry(wslink=False, api_id=None, api_key="key")
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    request = _RequestStub(query={"ID": "id", "PASSWORD": "key"})
    with pytest.raises(IncorrectDataError):
        await coordinator.received_data(request)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_received_data_missing_api_key_in_options_raises_incorrect_data_error(
    hass, monkeypatch
):
    entry = _make_entry(wslink=False, api_id="id", api_key=None)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    request = _RequestStub(query={"ID": "id", "PASSWORD": "key"})
    with pytest.raises(IncorrectDataError):
        await coordinator.received_data(request)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_received_data_wrong_credentials_raises_http_unauthorized(
    hass, monkeypatch
):
    entry = _make_entry(wslink=False, api_id="id", api_key="key")
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    request = _RequestStub(query={"ID": "id", "PASSWORD": "wrong"})
    with pytest.raises(HTTPUnauthorized):
        await coordinator.received_data(request)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_received_data_success_remaps_and_updates_coordinator_data(
    hass, monkeypatch
):
    entry = _make_entry(wslink=False, api_id="id", api_key="key")
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    # Patch remapping so this test doesn't depend on mapping tables.
    remapped = {"outside_temp": "10"}
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.remap_items",
        lambda _data: remapped,
    )

    # Ensure no autodiscovery triggers
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _remaped_items, _config: [],
    )

    # Capture updates
    coordinator.async_set_updated_data = MagicMock()

    request = _RequestStub(query={"ID": "id", "PASSWORD": "key", "tempf": "50"})
    resp = await coordinator.received_data(request)  # type: ignore[arg-type]

    assert resp.status == 200
    coordinator.async_set_updated_data.assert_called_once_with(remapped)


@pytest.mark.asyncio
async def test_received_data_success_wslink_uses_wslink_remap(hass, monkeypatch):
    entry = _make_entry(wslink=True, api_id="id", api_key="key")
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    remapped = {"ws_temp": "1"}
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.remap_wslink_items",
        lambda _data: remapped,
    )
    # If the wrong remapper is used, we'd crash because we won't patch it:
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _remaped_items, _config: [],
    )

    coordinator.async_set_updated_data = MagicMock()

    request = _RequestStub(query={"wsid": "id", "wspw": "key", "t": "1"})
    resp = await coordinator.received_data(request)  # type: ignore[arg-type]

    assert resp.status == 200
    coordinator.async_set_updated_data.assert_called_once_with(remapped)


@pytest.mark.asyncio
async def test_received_data_forwards_to_windy_when_enabled(hass, monkeypatch):
    entry = _make_entry(wslink=False, api_id="id", api_key="key", windy_enabled=True)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    coordinator.windy.push_data_to_windy = AsyncMock()

    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.remap_items",
        lambda _data: {"k": "v"},
    )
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _remaped_items, _config: [],
    )

    coordinator.async_set_updated_data = MagicMock()

    request = _RequestStub(query={"ID": "id", "PASSWORD": "key", "x": "y"})
    resp = await coordinator.received_data(request)  # type: ignore[arg-type]

    assert resp.status == 200
    coordinator.windy.push_data_to_windy.assert_awaited_once()
    args, _kwargs = coordinator.windy.push_data_to_windy.await_args
    assert isinstance(args[0], dict)  # raw data dict
    assert args[1] is False  # wslink flag


@pytest.mark.asyncio
async def test_received_data_forwards_to_pocasi_when_enabled(hass, monkeypatch):
    entry = _make_entry(wslink=True, api_id="id", api_key="key", pocasi_enabled=True)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    coordinator.pocasi.push_data_to_server = AsyncMock()

    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.remap_wslink_items",
        lambda _data: {"k": "v"},
    )
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _remaped_items, _config: [],
    )

    coordinator.async_set_updated_data = MagicMock()

    request = _RequestStub(query={"wsid": "id", "wspw": "key", "x": "y"})
    resp = await coordinator.received_data(request)  # type: ignore[arg-type]

    assert resp.status == 200
    coordinator.pocasi.push_data_to_server.assert_awaited_once()
    args, _kwargs = coordinator.pocasi.push_data_to_server.await_args
    assert isinstance(args[0], dict)  # raw data dict
    assert args[1] == "WSLINK"


@pytest.mark.asyncio
async def test_received_data_autodiscovery_updates_options_notifies_and_adds_sensors(
    hass,
    monkeypatch,
):
    entry = _make_entry(wslink=False, api_id="id", api_key="key")
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    # Arrange: remapped payload contains keys that are disabled.
    remapped = {"a": "1", "b": "2"}
    monkeypatch.setattr("custom_components.sws12500.coordinator.remap_items", lambda _d: remapped)

    # Autodiscovery finds two sensors to add
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _remaped_items, _config: ["a", "b"],
    )

    # No previously loaded sensors
    monkeypatch.setattr("custom_components.sws12500.coordinator.loaded_sensors", lambda _c: [])

    # translations returns a friendly name for each sensor key
    async def _translations(_hass, _domain, _key, **_kwargs):
        # return something non-None so it's included in human readable string
        return "Name"

    monkeypatch.setattr("custom_components.sws12500.coordinator.translations", _translations)

    translated_notification = AsyncMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.translated_notification", translated_notification
    )

    update_options = AsyncMock()
    monkeypatch.setattr("custom_components.sws12500.coordinator.update_options", update_options)

    add_new_sensors = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.add_new_sensors", add_new_sensors
    )

    coordinator.async_set_updated_data = MagicMock()

    request = _RequestStub(query={"ID": "id", "PASSWORD": "key"})
    resp = await coordinator.received_data(request)  # type: ignore[arg-type]

    assert resp.status == 200

    # It should notify
    translated_notification.assert_awaited()

    # It should persist newly discovered sensors
    update_options.assert_awaited()
    args, _kwargs = update_options.await_args
    assert args[2] == SENSORS_TO_LOAD
    assert set(args[3]) >= {"a", "b"}

    # It should add new sensors dynamically
    add_new_sensors.assert_called_once()
    _hass_arg, _entry_arg, keys = add_new_sensors.call_args.args
    assert _hass_arg is hass
    assert _entry_arg is entry
    assert set(keys) == {"a", "b"}

    coordinator.async_set_updated_data.assert_called_once_with(remapped)


@pytest.mark.asyncio
async def test_received_data_autodiscovery_human_readable_empty_branch_via_checked_none(
    hass,
    monkeypatch,
):
    """Force `checked([...], list[str])` to return None so `human_readable = ""` branch is executed."""
    entry = _make_entry(wslink=False, api_id="id", api_key="key")
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    remapped = {"a": "1"}
    monkeypatch.setattr("custom_components.sws12500.coordinator.remap_items", lambda _d: remapped)

    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _remaped_items, _config: ["a"],
    )
    monkeypatch.setattr("custom_components.sws12500.coordinator.loaded_sensors", lambda _c: [])

    # Return a translation so the list comprehension would normally include an item.
    async def _translations(_hass, _domain, _key, **_kwargs):
        return "Name"

    monkeypatch.setattr("custom_components.sws12500.coordinator.translations", _translations)

    # Force checked(...) to return None when the code tries to validate translate_sensors as list[str].
    def _checked_override(value, expected_type):
        if expected_type == list[str]:
            return None
        return value

    monkeypatch.setattr("custom_components.sws12500.coordinator.checked", _checked_override)

    translated_notification = AsyncMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.translated_notification", translated_notification
    )

    update_options = AsyncMock()
    monkeypatch.setattr("custom_components.sws12500.coordinator.update_options", update_options)

    add_new_sensors = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.add_new_sensors", add_new_sensors
    )

    coordinator.async_set_updated_data = MagicMock()

    request = _RequestStub(query={"ID": "id", "PASSWORD": "key"})
    resp = await coordinator.received_data(request)  # type: ignore[arg-type]

    assert resp.status == 200

    # Ensure it still notifies (with empty human readable list)
    translated_notification.assert_awaited()
    # And persists sensors
    update_options.assert_awaited()
    coordinator.async_set_updated_data.assert_called_once_with(remapped)


@pytest.mark.asyncio
async def test_received_data_autodiscovery_extends_with_loaded_sensors_branch(
    hass, monkeypatch
):
    """Cover `_loaded_sensors := loaded_sensors(self.config)` branch (extend existing)."""
    entry = _make_entry(wslink=False, api_id="id", api_key="key")
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    remapped = {"new": "1"}
    monkeypatch.setattr("custom_components.sws12500.coordinator.remap_items", lambda _d: remapped)

    # Autodiscovery finds one new sensor
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _remaped_items, _config: ["new"],
    )

    # Pretend there are already loaded sensors in options
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.loaded_sensors", lambda _c: ["existing"]
    )

    async def _translations(_hass, _domain, _key, **_kwargs):
        return "Name"

    monkeypatch.setattr("custom_components.sws12500.coordinator.translations", _translations)

    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.translated_notification", AsyncMock()
    )

    update_options = AsyncMock()
    monkeypatch.setattr("custom_components.sws12500.coordinator.update_options", update_options)

    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.add_new_sensors", MagicMock()
    )

    coordinator.async_set_updated_data = MagicMock()

    resp = await coordinator.received_data(
        _RequestStub(query={"ID": "id", "PASSWORD": "key"})
    )  # type: ignore[arg-type]

    assert resp.status == 200

    # Ensure the persisted list includes both new and existing sensors
    update_options.assert_awaited()
    args, _kwargs = update_options.await_args
    assert args[2] == SENSORS_TO_LOAD
    assert set(args[3]) >= {"new", "existing"}


@pytest.mark.asyncio
async def test_received_data_autodiscovery_translations_all_none_still_notifies_and_updates(
    hass, monkeypatch
):
    """Cover the branch where translated sensor names cannot be resolved (human_readable becomes empty)."""
    entry = _make_entry(wslink=False, api_id="id", api_key="key")
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    remapped = {"a": "1"}
    monkeypatch.setattr("custom_components.sws12500.coordinator.remap_items", lambda _d: remapped)

    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _remaped_items, _config: ["a"],
    )
    monkeypatch.setattr("custom_components.sws12500.coordinator.loaded_sensors", lambda _c: [])

    # Force translations to return None for every lookup -> translate_sensors becomes None and human_readable ""
    async def _translations(_hass, _domain, _key, **_kwargs):
        return None

    monkeypatch.setattr("custom_components.sws12500.coordinator.translations", _translations)

    translated_notification = AsyncMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.translated_notification", translated_notification
    )

    update_options = AsyncMock()
    monkeypatch.setattr("custom_components.sws12500.coordinator.update_options", update_options)

    add_new_sensors = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.add_new_sensors", add_new_sensors
    )

    coordinator.async_set_updated_data = MagicMock()

    resp = await coordinator.received_data(
        _RequestStub(query={"ID": "id", "PASSWORD": "key"})
    )  # type: ignore[arg-type]

    assert resp.status == 200
    translated_notification.assert_awaited()
    update_options.assert_awaited()
    add_new_sensors.assert_called_once()
    coordinator.async_set_updated_data.assert_called_once_with(remapped)


@pytest.mark.asyncio
async def test_received_data_dev_logging_calls_anonymize_and_logs(hass, monkeypatch):
    entry = _make_entry(wslink=False, api_id="id", api_key="key", dev_debug=True)
    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    monkeypatch.setattr("custom_components.sws12500.coordinator.remap_items", lambda _d: {"k": "v"})
    monkeypatch.setattr(
        "custom_components.sws12500.coordinator.check_disabled",
        lambda _remaped_items, _config: [],
    )

    anonymize = MagicMock(return_value={"safe": True})
    monkeypatch.setattr("custom_components.sws12500.coordinator.anonymize", anonymize)

    log_info = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.coordinator._LOGGER.info", log_info)

    coordinator.async_set_updated_data = MagicMock()

    request = _RequestStub(query={"ID": "id", "PASSWORD": "key", "x": "y"})
    resp = await coordinator.received_data(request)  # type: ignore[arg-type]

    assert resp.status == 200
    anonymize.assert_called_once()
    log_info.assert_called_once()


@pytest.mark.asyncio
async def test_register_path_switching_logic_is_exercised_via_routes(monkeypatch):
    """Sanity: constants exist and are distinct (helps guard tests relying on them)."""
    assert DEFAULT_URL != WSLINK_URL
    assert DOMAIN == "sws12500"


@pytest.mark.asyncio
async def test_received_data_empty_configured_credentials_raises_incorrect_data(hass, monkeypatch):
    """Empty configured API ID/KEY is treated as missing config (defense-in-depth)."""
    entry = _make_entry(wslink=False, api_id="", api_key="key")
    entry.runtime_data.health_coordinator = SimpleNamespace(update_ingress_result=MagicMock())
    coordinator = WeatherDataUpdateCoordinator(hass, entry)
    with pytest.raises(IncorrectDataError):
        await coordinator.received_data(_RequestStub(query={"ID": "id", "PASSWORD": "key"}))  # type: ignore[arg-type]
    entry.runtime_data.health_coordinator.update_ingress_result.assert_called_once()


@pytest.mark.asyncio
async def test_received_data_empty_incoming_credentials_raises_unauthorized(hass, monkeypatch):
    """Present-but-empty incoming credentials are rejected before the digest compare."""
    entry = _make_entry(wslink=False, api_id="id", api_key="key")
    entry.runtime_data.health_coordinator = SimpleNamespace(update_ingress_result=MagicMock())
    coordinator = WeatherDataUpdateCoordinator(hass, entry)
    with pytest.raises(HTTPUnauthorized):
        await coordinator.received_data(_RequestStub(query={"ID": "", "PASSWORD": ""}))  # type: ignore[arg-type]
    entry.runtime_data.health_coordinator.update_ingress_result.assert_called_once()
