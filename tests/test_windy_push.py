from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiohttp.client_exceptions import ClientError
import pytest

from custom_components.sws12500.const import (
    PURGE_DATA,
    WINDY_ENABLED,
    WINDY_LOGGER_ENABLED,
    WINDY_STATION_ID,
    WINDY_STATION_PW,
    WINDY_UNEXPECTED,
    WINDY_URL,
)
from custom_components.sws12500.windy_func import WindyNotInserted, WindyPasswordMissing, WindyPush, WindySuccess
from homeassistant.util import dt as dt_util


@dataclass(slots=True)
class _FakeResponse:
    status: int
    text_value: str = ""

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

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.calls.append(
            {"url": url, "params": dict(params or {}), "headers": dict(headers or {})}
        )
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


@pytest.fixture
def hass():
    # Use HA provided fixture if available; otherwise a minimal stub works because we patch session getter.
    return SimpleNamespace()


def _make_entry(**options: Any):
    defaults = {
        WINDY_LOGGER_ENABLED: False,
        WINDY_ENABLED: True,
        WINDY_STATION_ID: "station",
        WINDY_STATION_PW: "token",
    }
    defaults.update(options)
    return SimpleNamespace(options=defaults)


def test_verify_windy_response_notice_raises_not_inserted(hass):
    wp = WindyPush(hass, _make_entry())
    with pytest.raises(WindyNotInserted):
        wp.verify_windy_response(_FakeResponse(status=400, text_value="Bad Request"))


def test_verify_windy_response_success_raises_success(hass):
    wp = WindyPush(hass, _make_entry())
    with pytest.raises(WindySuccess):
        wp.verify_windy_response(_FakeResponse(status=200, text_value="OK"))


def test_verify_windy_response_password_missing_raises(hass):
    wp = WindyPush(hass, _make_entry())
    with pytest.raises(WindyPasswordMissing):
        wp.verify_windy_response(_FakeResponse(status=401, text_value="Unauthorized"))


def test_covert_wslink_to_pws_maps_keys(hass):
    wp = WindyPush(hass, _make_entry())
    data = {
        "t1ws": "1",
        "t1wgust": "2",
        "t1wdir": "3",
        "t1hum": "4",
        "t1dew": "5",
        "t1tem": "6",
        "rbar": "7",
        "t1rainhr": "8",
        "t1uvi": "9",
        "t1solrad": "10",
        "other": "keep",
    }
    out = wp._covert_wslink_to_pws(data)
    assert out["wind"] == "1"
    assert out["gust"] == "2"
    assert out["winddir"] == "3"
    assert out["humidity"] == "4"
    assert out["dewpoint"] == "5"
    assert out["temp"] == "6"
    assert out["mbar"] == "7"
    assert out["precip"] == "8"
    assert out["uv"] == "9"
    assert out["solarradiation"] == "10"
    assert out["other"] == "keep"
    for k in (
        "t1ws",
        "t1wgust",
        "t1wdir",
        "t1hum",
        "t1dew",
        "t1tem",
        "rbar",
        "t1rainhr",
        "t1uvi",
        "t1solrad",
    ):
        assert k not in out


@pytest.mark.asyncio
async def test_push_data_to_windy_respects_initial_next_update(monkeypatch, hass):
    entry = _make_entry()
    wp = WindyPush(hass, entry)

    # Ensure "next_update > now" is true
    wp.next_update = dt_util.utcnow() + timedelta(minutes=10)

    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: _FakeSession(response=_FakeResponse(status=200, text_value="OK")),
    )
    ok = await wp.push_data_to_windy({"a": "b"})
    assert ok is False


@pytest.mark.asyncio
async def test_push_data_to_windy_purges_data_and_sets_auth(monkeypatch, hass):
    entry = _make_entry(**{WINDY_LOGGER_ENABLED: True})
    wp = WindyPush(hass, entry)

    # Force it to send now
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse(status=200, text_value="OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: session,
    )

    data = {k: "x" for k in PURGE_DATA}
    data.update({"keep": "1"})
    ok = await wp.push_data_to_windy(data, wslink=False)
    assert ok is True

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == WINDY_URL
    # Purged keys removed
    for k in PURGE_DATA:
        assert k not in call["params"]
    # Added keys
    assert call["params"]["id"] == entry.options[WINDY_STATION_ID]
    assert call["params"]["time"] == "now"
    assert (
        call["headers"]["Authorization"] == f"Bearer {entry.options[WINDY_STATION_PW]}"
    )


@pytest.mark.asyncio
async def test_push_data_to_windy_wslink_conversion_applied(monkeypatch, hass):
    entry = _make_entry()
    wp = WindyPush(hass, entry)
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse(status=200, text_value="OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: session,
    )

    ok = await wp.push_data_to_windy({"t1ws": "1", "t1tem": "2"}, wslink=True)
    assert ok is True
    params = session.calls[0]["params"]
    assert "wind" in params and params["wind"] == "1"
    assert "temp" in params and params["temp"] == "2"
    assert "t1ws" not in params and "t1tem" not in params


@pytest.mark.asyncio
async def test_push_data_to_windy_missing_station_id_returns_false(monkeypatch, hass):
    entry = _make_entry()
    entry.options.pop(WINDY_STATION_ID)
    wp = WindyPush(hass, entry)
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse(status=200, text_value="OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: session,
    )

    update_options = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.update_options", update_options
    )
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.persistent_notification.async_create",
        MagicMock(),
    )

    ok = await wp.push_data_to_windy({"a": "b"})
    assert ok is False
    assert session.calls == []
    # Disabling must not overwrite the specific reason the diagnostics sensor reports.
    assert wp.last_status == "config_error"


@pytest.mark.asyncio
async def test_push_data_to_windy_missing_station_pw_returns_false(monkeypatch, hass):
    entry = _make_entry()
    entry.options.pop(WINDY_STATION_PW)
    wp = WindyPush(hass, entry)
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse(status=200, text_value="OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: session,
    )

    update_options = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.update_options", update_options
    )
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.persistent_notification.async_create",
        MagicMock(),
    )

    ok = await wp.push_data_to_windy({"a": "b"})
    assert ok is False
    assert session.calls == []
    assert wp.last_status == "config_error"


@pytest.mark.asyncio
async def test_push_data_to_windy_invalid_api_key_disables_windy(monkeypatch, hass):
    entry = _make_entry()
    wp = WindyPush(hass, entry)
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    # Response triggers WindyPasswordMissing (401)
    session = _FakeSession(
        response=_FakeResponse(status=401, text_value="Unauthorized")
    )
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: session,
    )

    update_options = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.update_options", update_options
    )
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.persistent_notification.async_create",
        MagicMock(),
    )

    ok = await wp.push_data_to_windy({"a": "b"})
    assert ok is True
    update_options.assert_awaited_once_with(hass, entry, WINDY_ENABLED, False)
    assert wp.last_status == "auth_error"


@pytest.mark.asyncio
async def test_push_data_to_windy_invalid_api_key_update_options_failure_logs_debug(
    monkeypatch, hass
):
    entry = _make_entry()
    wp = WindyPush(hass, entry)
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(
        response=_FakeResponse(status=401, text_value="Unauthorized")
    )
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: session,
    )

    update_options = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.update_options", update_options
    )

    dbg = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.windy_func._LOGGER.debug", dbg)
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.persistent_notification.async_create",
        MagicMock(),
    )

    ok = await wp.push_data_to_windy({"a": "b"})
    assert ok is True
    update_options.assert_awaited_once_with(hass, entry, WINDY_ENABLED, False)
    dbg.assert_called()


@pytest.mark.asyncio
async def test_push_data_to_windy_notice_logs_not_inserted(monkeypatch, hass):
    entry = _make_entry(**{WINDY_LOGGER_ENABLED: True})
    wp = WindyPush(hass, entry)
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse(status=400, text_value="Bad Request"))
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: session,
    )

    err = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.windy_func._LOGGER.error", err)

    ok = await wp.push_data_to_windy({"a": "b"})
    assert ok is True
    # It logs WINDY_NOT_INSERTED regardless of log setting
    err.assert_called()


@pytest.mark.asyncio
async def test_push_data_to_windy_success_logs_info_when_logger_enabled(
    monkeypatch, hass
):
    entry = _make_entry(**{WINDY_LOGGER_ENABLED: True})
    wp = WindyPush(hass, entry)
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse(status=200, text_value="OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: session,
    )

    info = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.windy_func._LOGGER.info", info)

    ok = await wp.push_data_to_windy({"a": "b"})
    assert ok is True
    # It should log WINDY_SUCCESS (or at least call info) when logging is enabled
    info.assert_called()


@pytest.mark.asyncio
async def test_push_data_to_windy_verify_no_raise_logs_debug_not_inserted_when_logger_enabled(
    monkeypatch, hass
):
    """Cover the `else:` branch when `verify_windy_response` does not raise.

    This is a defensive branch in `push_data_to_windy`:
        try: verify(...)
        except ...:
        else:
            if self.log:
                _LOGGER.debug(WINDY_NOT_INSERTED)
    """
    entry = _make_entry(**{WINDY_LOGGER_ENABLED: True})
    wp = WindyPush(hass, entry)
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    # Response text that does not contain any of the known markers (NOTICE/SUCCESS/Invalid/Unauthorized)
    session = _FakeSession(response=_FakeResponse(status=500, text_value="Error"))
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: session,
    )

    debug = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.windy_func._LOGGER.debug", debug)

    ok = await wp.push_data_to_windy({"a": "b"})
    assert ok is True
    debug.assert_called()


@pytest.mark.asyncio
async def test_push_data_to_windy_client_error_increments_and_disables_after_three(
    monkeypatch, hass
):
    entry = _make_entry()
    wp = WindyPush(hass, entry)
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    update_options = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.update_options", update_options
    )

    crit = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.windy_func._LOGGER.critical", crit)
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.persistent_notification.async_create",
        MagicMock(),
    )

    # Cause ClientError on session.get
    session = _FakeSession(exc=ClientError("boom"))
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: session,
    )

    # First 3 calls should not disable; 4th should
    for i in range(4):
        wp.next_update = dt_util.utcnow() - timedelta(seconds=1)
        ok = await wp.push_data_to_windy({"a": "b"})
        assert ok is True

    assert wp.invalid_response_count == 4
    # update_options awaited once when count > 3
    update_options.assert_awaited()
    args = update_options.await_args.args
    assert args[2] == WINDY_ENABLED
    assert args[3] is False
    # It should log WINDY_UNEXPECTED at least once
    assert any(
        WINDY_UNEXPECTED in str(c.args[0]) for c in crit.call_args_list if c.args
    )


@pytest.mark.asyncio
async def test_push_data_to_windy_timeout_is_handled_like_client_error(
    monkeypatch, hass
):
    """A network timeout must not escape into the webhook handler.

    `TimeoutError` is not a subclass of `ClientError`, so it used to propagate out
    of `push_data_to_windy`, through the awaiting coordinator, and answer the
    station with HTTP 500 - even though the measured data was already stored.
    """
    entry = _make_entry()
    wp = WindyPush(hass, entry)
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.update_options", AsyncMock(return_value=True)
    )
    monkeypatch.setattr("custom_components.sws12500.windy_func._LOGGER.critical", MagicMock())
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.persistent_notification.async_create",
        MagicMock(),
    )

    session = _FakeSession(exc=TimeoutError("timed out"))
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: session,
    )

    ok = await wp.push_data_to_windy({"a": "b"})

    assert ok is True
    assert wp.last_status == "client_error"
    assert wp.last_error == "TimeoutError"
    assert wp.invalid_response_count == 1


@pytest.mark.asyncio
async def test_push_data_to_windy_client_error_disable_failure_logs_debug(
    monkeypatch, hass
):
    entry = _make_entry()
    wp = WindyPush(hass, entry)
    wp.invalid_response_count = 3  # next error will push it over the threshold
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    update_options = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.update_options", update_options
    )

    dbg = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.windy_func._LOGGER.debug", dbg)
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.persistent_notification.async_create",
        MagicMock(),
    )

    session = _FakeSession(exc=ClientError("boom"))
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: session,
    )

    ok = await wp.push_data_to_windy({"a": "b"})
    assert ok is True
    update_options.assert_awaited_once_with(hass, entry, WINDY_ENABLED, False)
    dbg.assert_called()
