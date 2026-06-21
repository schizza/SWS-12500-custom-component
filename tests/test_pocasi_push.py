from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock

from aiohttp import ClientError
import pytest

from custom_components.sws12500.const import (
    DEFAULT_URL,
    POCASI_CZ_API_ID,
    POCASI_CZ_API_KEY,
    POCASI_CZ_ENABLED,
    POCASI_CZ_LOGGER_ENABLED,
    POCASI_CZ_SEND_INTERVAL,
    POCASI_CZ_UNEXPECTED,
    POCASI_CZ_URL,
    POCASI_INVALID_KEY,
    WSLINK_URL,
)
from custom_components.sws12500.pocasti_cz import PocasiApiKeyError, PocasiPush, PocasiSuccess
from homeassistant.util import dt as dt_util


@dataclass(slots=True)
class _FakeResponse:
    text_value: str

    async def text(self) -> str:
        return self.text_value

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeSession:
    def __init__(
        self, *, response: _FakeResponse | None = None, exc: Exception | None = None
    ):
        self._response = response
        self._exc = exc
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: dict[str, Any] | None = None):
        self.calls.append({"url": url, "params": dict(params or {})})
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


def _make_entry(
    *,
    api_id: str | None = "id",
    api_key: str | None = "key",
    interval: int = 30,
    logger: bool = False,
) -> Any:
    options: dict[str, Any] = {
        POCASI_CZ_SEND_INTERVAL: interval,
        POCASI_CZ_LOGGER_ENABLED: logger,
        POCASI_CZ_ENABLED: True,
    }
    if api_id is not None:
        options[POCASI_CZ_API_ID] = api_id
    if api_key is not None:
        options[POCASI_CZ_API_KEY] = api_key

    entry = SimpleNamespace()
    entry.options = options
    entry.entry_id = "test_entry_id"
    return entry


@pytest.fixture
def hass():
    # Minimal hass-like object; we patch client session retrieval.
    return SimpleNamespace()


@pytest.mark.asyncio
async def test_push_data_to_server_missing_api_id_returns_early(monkeypatch, hass):
    entry = _make_entry(api_id=None, api_key="key")
    pp = PocasiPush(hass, entry)

    session = _FakeSession(response=_FakeResponse("OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )

    await pp.push_data_to_server({"x": 1}, "WU")
    assert session.calls == []


@pytest.mark.asyncio
async def test_push_data_to_server_missing_api_key_returns_early(monkeypatch, hass):
    entry = _make_entry(api_id="id", api_key=None)
    pp = PocasiPush(hass, entry)

    session = _FakeSession(response=_FakeResponse("OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )

    await pp.push_data_to_server({"x": 1}, "WU")
    assert session.calls == []


@pytest.mark.asyncio
async def test_push_data_to_server_respects_interval_limit(monkeypatch, hass):
    entry = _make_entry(interval=30, logger=True)
    pp = PocasiPush(hass, entry)

    # Ensure "next_update > now" so it returns early before doing HTTP.
    pp.next_update = dt_util.utcnow() + timedelta(seconds=999)

    session = _FakeSession(response=_FakeResponse("OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )

    await pp.push_data_to_server({"x": 1}, "WU")
    assert session.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,expected_path", [("WU", DEFAULT_URL), ("WSLINK", WSLINK_URL)]
)
async def test_push_data_to_server_injects_auth_and_chooses_url(
    monkeypatch, hass, mode: Literal["WU", "WSLINK"], expected_path: str
):
    entry = _make_entry(api_id="id", api_key="key")
    pp = PocasiPush(hass, entry)

    # Force send now.
    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse("OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )

    # Avoid depending on anonymize output; just make it deterministic.
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz.anonymize", lambda d: d)

    await pp.push_data_to_server({"temp": 1}, mode)

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == f"{POCASI_CZ_URL}{expected_path}"

    params = call["params"]
    if mode == "WU":
        assert params["ID"] == "id"
        assert params["PASSWORD"] == "key"
    else:
        assert params["wsid"] == "id"
        assert params["wspw"] == "key"


@pytest.mark.asyncio
async def test_push_data_to_server_calls_verify_response(monkeypatch, hass):
    entry = _make_entry()
    pp = PocasiPush(hass, entry)
    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse("OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz.anonymize", lambda d: d)

    verify = MagicMock(return_value=None)
    monkeypatch.setattr(pp, "verify_response", verify)

    await pp.push_data_to_server({"x": 1}, "WU")
    verify.assert_called_once_with("OK")


@pytest.mark.asyncio
async def test_push_data_to_server_api_key_error_disables_feature(monkeypatch, hass):
    entry = _make_entry()
    pp = PocasiPush(hass, entry)
    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse("OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz.anonymize", lambda d: d)

    def _raise(_status: str):
        raise PocasiApiKeyError

    monkeypatch.setattr(pp, "verify_response", _raise)

    update_options = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.update_options", update_options
    )

    crit = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz._LOGGER.critical", crit)

    await pp.push_data_to_server({"x": 1}, "WU")

    crit.assert_called()
    # Should log invalid key message and disable feature.
    assert any(
        POCASI_INVALID_KEY in str(c.args[0]) for c in crit.call_args_list if c.args
    )
    update_options.assert_awaited_once_with(hass, entry, POCASI_CZ_ENABLED, False)


@pytest.mark.asyncio
async def test_push_data_to_server_success_logs_when_logger_enabled(monkeypatch, hass):
    entry = _make_entry(logger=True)
    pp = PocasiPush(hass, entry)
    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse("OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz.anonymize", lambda d: d)

    def _raise_success(_status: str):
        raise PocasiSuccess

    monkeypatch.setattr(pp, "verify_response", _raise_success)

    info = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz._LOGGER.info", info)

    await pp.push_data_to_server({"x": 1}, "WU")
    info.assert_called()


@pytest.mark.asyncio
async def test_push_data_to_server_client_error_increments_and_disables_after_three(
    monkeypatch, hass
):
    entry = _make_entry()
    pp = PocasiPush(hass, entry)

    update_options = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.update_options", update_options
    )

    crit = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz._LOGGER.critical", crit)

    session = _FakeSession(exc=ClientError("boom"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )

    # Force request attempts and exceed invalid count threshold.
    for _i in range(4):
        pp.next_update = dt_util.utcnow() - timedelta(seconds=1)
        await pp.push_data_to_server({"x": 1}, "WU")

    assert pp.invalid_response_count == 4
    # Should disable after >3
    update_options.assert_awaited()
    args = update_options.await_args.args
    assert args[2] == POCASI_CZ_ENABLED
    assert args[3] is False
    # Should log unexpected at least once
    assert any(
        POCASI_CZ_UNEXPECTED in str(c.args[0]) for c in crit.call_args_list if c.args
    )


def test_verify_response_logs_debug_when_logger_enabled(monkeypatch, hass):
    entry = _make_entry(logger=True)
    pp = PocasiPush(hass, entry)

    dbg = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz._LOGGER.debug", dbg)

    assert pp.verify_response("anything") is None
    dbg.assert_called()
