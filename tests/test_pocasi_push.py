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
    POCASI_CZ_MAX_RETRIES,
    POCASI_CZ_SEND_INTERVAL,
    POCASI_CZ_UNEXPECTED,
    POCASI_CZ_URL,
    POCASI_INVALID_KEY,
    WSLINK_URL,
)
from custom_components.sws12500.pocasti_cz import PocasiPush
from homeassistant.util import dt as dt_util


@dataclass(slots=True)
class _FakeResponse:
    text_value: str
    status: int = 200

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

    def get(self, url: str, *, params: dict[str, Any] | None = None, timeout: Any = None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
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



def _write_through_update_options(entry: Any) -> AsyncMock:
    """Mock `update_options` that really mutates the entry, like the real helper.

    `PocasiPush.enabled` reads the option back, so a mock that only records the call
    would leave `enabled` reporting the pre-disable value.
    """

    async def _apply(_hass, _entry, key, value):
        entry.options[key] = value
        return True

    return AsyncMock(side_effect=_apply)


@pytest.fixture
def hass():
    # Minimal hass-like object; we patch client session retrieval.
    return SimpleNamespace()


@pytest.fixture(autouse=True)
def notify(monkeypatch):
    """Capture the disable notification; the stub `hass` cannot serve the real one."""
    created = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.persistent_notification.async_create", created
    )
    return created


@pytest.mark.parametrize("stored", ["", "abc", None, [], 0])
def test_unreadable_send_interval_falls_back_to_the_default(hass, stored):
    """A corrupted option must not take the whole entry setup down.

    `PocasiPush` is constructed from the coordinator during `async_setup_entry`, so a
    raise here means the integration fails to load rather than forwarding late.
    """
    from custom_components.sws12500.const import POCASI_CZ_SEND_DEFAULT

    entry = _make_entry()
    entry.options[POCASI_CZ_SEND_INTERVAL] = stored

    assert PocasiPush(hass, entry)._interval == POCASI_CZ_SEND_DEFAULT


def test_a_stored_send_interval_is_honoured(hass):
    entry = _make_entry(interval=45)
    assert PocasiPush(hass, entry)._interval == 45


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

    verify = MagicMock(return_value="ok")
    monkeypatch.setattr(pp, "verify_response", verify)

    await pp.push_data_to_server({"x": 1}, "WU")
    verify.assert_called_once_with(200, "OK")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_push_data_to_server_auth_error_disables_feature(monkeypatch, hass, status):
    """A 401/403 disables resending immediately - credentials will not self-heal."""
    entry = _make_entry()
    pp = PocasiPush(hass, entry)
    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse("", status=status))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz.anonymize", lambda d: d)

    update_options = _write_through_update_options(entry)
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
    assert pp.enabled is False
    assert pp.last_status == "auth_error"


@pytest.mark.asyncio
async def test_push_data_to_server_success_logs_when_logger_enabled(monkeypatch, hass):
    entry = _make_entry(logger=True)
    pp = PocasiPush(hass, entry)
    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)
    # A previous failure must be cleared by a successful send.
    pp.invalid_response_count = 2

    session = _FakeSession(response=_FakeResponse("OK", status=200))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz.anonymize", lambda d: d)

    info = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz._LOGGER.info", info)

    await pp.push_data_to_server({"x": 1}, "WU")

    info.assert_called()
    assert pp.last_status == "ok"
    assert pp.last_error is None
    assert pp.invalid_response_count == 0


@pytest.mark.asyncio
async def test_push_data_to_server_server_error_disables_after_max_retries(monkeypatch, hass):
    """HTTP 500 is no longer silently reported as success; it counts toward the limit."""
    entry = _make_entry()
    pp = PocasiPush(hass, entry)

    session = _FakeSession(response=_FakeResponse("", status=500))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz.anonymize", lambda d: d)

    update_options = _write_through_update_options(entry)
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.update_options", update_options
    )

    for _ in range(POCASI_CZ_MAX_RETRIES - 1):
        pp.next_update = dt_util.utcnow() - timedelta(seconds=1)
        await pp.push_data_to_server({"x": 1}, "WU")

    assert pp.last_status == "unexpected_response"
    assert pp.enabled is True
    update_options.assert_not_awaited()

    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)
    await pp.push_data_to_server({"x": 1}, "WU")

    assert pp.enabled is False
    update_options.assert_awaited_once_with(hass, entry, POCASI_CZ_ENABLED, False)


@pytest.mark.asyncio
async def test_push_data_to_server_client_error_increments_and_disables_after_three(
    monkeypatch, hass
):
    entry = _make_entry()
    pp = PocasiPush(hass, entry)

    update_options = _write_through_update_options(entry)
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


@pytest.mark.asyncio
async def test_push_data_to_server_timeout_is_caught_and_not_counted(monkeypatch, hass):
    """A network timeout must not escape into the webhook handler.

    `TimeoutError` is not a subclass of `ClientError`, so it used to propagate out
    of `push_data_to_server`, through the awaiting coordinator, and answer the
    station with HTTP 500 - even though the measured data was already stored.

    It must not spend the retry budget either: a slow upstream is transient, so the
    next push simply tries again.
    """
    entry = _make_entry()
    pp = PocasiPush(hass, entry)

    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.update_options",
        _write_through_update_options(entry),
    )
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz._LOGGER.critical", MagicMock())

    session = _FakeSession(exc=TimeoutError("timed out"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )

    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)
    await pp.push_data_to_server({"x": 1}, "WU")

    assert pp.last_status == "timeout"
    assert pp.last_error == "TimeoutError"
    assert pp.invalid_response_count == 0
    assert pp.enabled is True


@pytest.mark.asyncio
async def test_repeated_timeouts_never_disable_pocasi(monkeypatch, hass, notify):
    """Two minutes of a merely slow server must not turn forwarding off for good.

    With a 30 second send interval, counting timeouts would spend the whole retry
    budget on a slowdown that recovers by itself.
    """
    entry = _make_entry()
    pp = PocasiPush(hass, entry)

    update_options = _write_through_update_options(entry)
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.update_options", update_options
    )

    session = _FakeSession(exc=TimeoutError("timed out"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )

    for _ in range(POCASI_CZ_MAX_RETRIES + 2):
        pp.next_update = dt_util.utcnow() - timedelta(seconds=1)
        await pp.push_data_to_server({"x": 1}, "WU")

    assert pp.invalid_response_count == 0
    assert pp.enabled is True
    update_options.assert_not_awaited()
    notify.assert_not_called()


@pytest.mark.asyncio
async def test_timeout_does_not_reset_an_existing_client_error_budget(monkeypatch, hass):
    """A timeout is ignored by the counter, not a substitute for a successful send."""
    entry = _make_entry()
    pp = PocasiPush(hass, entry)
    pp.invalid_response_count = 2
    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(exc=TimeoutError("timed out"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )

    await pp.push_data_to_server({"x": 1}, "WU")

    assert pp.invalid_response_count == 2


@pytest.mark.asyncio
async def test_disabling_pocasi_notifies_the_user(monkeypatch, hass, notify):
    """Forwarding switching itself off must be visible, not just a log line.

    Windy already raises a persistent notification; without one here the user only
    finds out when data stops arriving upstream.
    """
    entry = _make_entry()
    pp = PocasiPush(hass, entry)
    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse("", status=401))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz.anonymize", lambda d: d)
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.update_options",
        _write_through_update_options(entry),
    )
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz._LOGGER.critical", MagicMock())

    await pp.push_data_to_server({"x": 1}, "WU")

    assert pp.enabled is False
    notify.assert_called_once()
    args = notify.call_args.args
    assert args[0] is hass
    assert POCASI_INVALID_KEY in args[1]


@pytest.mark.asyncio
async def test_push_data_to_server_bounds_the_request(monkeypatch, hass):
    """The send must carry an explicit timeout.

    Home Assistant's shared session sets none, so aiohttp's 5 minute default would
    hold the station's own webhook open long past the point where it gives up - and
    the TimeoutError branch above could never run in time to matter.
    """
    from custom_components.sws12500.const import FORWARD_TIMEOUT

    pp = PocasiPush(hass, _make_entry())

    session = _FakeSession(response=_FakeResponse(status=200, text_value="OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )

    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)
    await pp.push_data_to_server({"tempf": "68"}, "WU")

    timeout = session.calls[0]["timeout"]
    assert timeout is not None
    assert timeout.total == FORWARD_TIMEOUT
    assert 0 < timeout.total <= 30


def test_verify_response_logs_debug_when_logger_enabled(monkeypatch, hass):
    entry = _make_entry(logger=True)
    pp = PocasiPush(hass, entry)

    dbg = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz._LOGGER.debug", dbg)

    assert pp.verify_response(200, "anything") == "ok"
    dbg.assert_called()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, "ok"),
        (204, "ok"),
        (299, "ok"),
        (401, "auth_error"),
        (403, "auth_error"),
        (400, "unexpected_response"),
        (404, "unexpected_response"),
        (500, "unexpected_response"),
        (503, "unexpected_response"),
    ],
)
def test_verify_response_status_mapping(hass, status, expected):
    """Every send outcome is derived from the HTTP status, not from the (empty) body."""
    pp = PocasiPush(hass, _make_entry())
    assert pp.verify_response(status, "") == expected


@pytest.mark.asyncio
async def test_disable_pocasi_logs_when_option_write_fails(monkeypatch, hass):
    """A failed option write is logged but still leaves resending off in memory."""
    entry = _make_entry()
    pp = PocasiPush(hass, entry)

    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.update_options",
        AsyncMock(return_value=False),
    )
    dbg = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz._LOGGER.debug", dbg)

    await pp._disable_pocasi("because")

    # `enabled` mirrors the persisted option: if the write failed, forwarding is still
    # on as far as the config is concerned, and the failure is logged instead.
    assert pp.enabled is True
    assert pp.last_error == "because"
    dbg.assert_called()


# ---------------------------------------------------------------------------
# Live `enabled` and empty-credential rejection
# ---------------------------------------------------------------------------


def test_enabled_reads_options_live(hass):
    """Toggling the option is visible immediately - no reload, no cached copy.

    `update_listener` deliberately skips the reload when only this flag changes, so a
    value cached in __init__ would leave the diagnostics sensor permanently stale.
    """
    entry = _make_entry()
    pp = PocasiPush(hass, entry)
    assert pp.enabled is True

    entry.options[POCASI_CZ_ENABLED] = False
    assert pp.enabled is False

    entry.options[POCASI_CZ_ENABLED] = True
    assert pp.enabled is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("api_id", "api_key"),
    [("", "key"), ("id", ""), ("", "")],
    ids=["empty-id", "empty-key", "both-empty"],
)
async def test_empty_credentials_never_reach_the_network(monkeypatch, hass, api_id, api_key):
    """An empty string is still a `str`, so it must be rejected explicitly.

    Otherwise a blank configuration sends a request that can only ever be refused.
    """
    entry = _make_entry(api_id=api_id, api_key=api_key)
    pp = PocasiPush(hass, entry)
    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    session = _FakeSession(response=_FakeResponse("OK"))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )

    await pp.push_data_to_server({"x": 1}, "WU")

    assert session.calls == []
    assert pp.last_status == "config_error"
