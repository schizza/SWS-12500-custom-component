"""Forwarding an Ecowitt payload to Pocasi Meteo.

Their integration notes are specific, and every detail here is load-bearing:

- Ecowitt is accepted **only as a POST** in the Ecowitt protocol; the payload is
  forwarded verbatim rather than translated into PWS field names.
- The endpoint is ``/ws_ecowitt/ws.php`` (not the PWS one).
- The account credentials go in the **query string**, and the password parameter is
  ``PAS`` - not ``PASS`` or ``PASSWORD`` as on the PWS endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.sws12500.const import (
    DEFAULT_URL,
    POCASI_CZ_API_ID,
    POCASI_CZ_API_KEY,
    POCASI_CZ_ECOWITT_URL,
    POCASI_CZ_ENABLED,
    POCASI_CZ_LOGGER_ENABLED,
    POCASI_CZ_SEND_INTERVAL,
    POCASI_CZ_URL,
)
from custom_components.sws12500.pocasti_cz import PocasiPush
from homeassistant.util import dt as dt_util

# A representative Ecowitt POST body, including the metadata a station really sends.
ECOWITT_PAYLOAD: dict[str, str] = {
    "PASSKEY": "A1B2C3D4E5F6",
    "stationtype": "GW1000B_V1.6.8",
    "dateutc": "2026-07-26 01:09:02",
    "tempinf": "53.4",
    "humidityin": "76",
    "baromrelin": "28.792",
    "baromabsin": "28.792",
    "tempf": "43.2",
    "humidity": "40",
    "dewpointf": "20.3",
    "winddir": "119",
    "windspeedmph": "6.9",
    "windgustmph": "9.7",
    "solarradiation": "7.0",
    "uv": "0",
    "dailyrainin": "3.55",
    "hourlyrainin": "2.08",
    "model": "GW1000",
    "freq": "868M",
}


@dataclass(slots=True)
class _FakeResponse:
    status: int = 200
    text_value: str = ""

    async def text(self) -> str:
        return self.text_value

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@dataclass
class _RecordingSession:
    """Records how the request was made: verb, url, query params and body."""

    response: _FakeResponse = field(default_factory=_FakeResponse)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def get(self, url: str, *, params: dict[str, Any] | None = None, **kw: Any):
        self.calls.append(
            {
                "verb": "GET",
                "url": url,
                "params": dict(params or {}),
                "body": kw.get("data"),
                "timeout": kw.get("timeout"),
            }
        )
        return self.response

    def post(self, url: str, *, params: dict[str, Any] | None = None, data: Any = None, **kw: Any):
        self.calls.append(
            {
                "verb": "POST",
                "url": url,
                "params": dict(params or {}),
                "body": data,
                "timeout": kw.get("timeout"),
            }
        )
        return self.response


def _make_entry(*, api_id: str = "myid", api_key: str = "mykey") -> Any:
    return SimpleNamespace(
        options={
            POCASI_CZ_API_ID: api_id,
            POCASI_CZ_API_KEY: api_key,
            POCASI_CZ_ENABLED: True,
            POCASI_CZ_LOGGER_ENABLED: False,
            POCASI_CZ_SEND_INTERVAL: 30,
        },
        entry_id="entry",
    )


@pytest.fixture
def hass():
    return SimpleNamespace()


@pytest.fixture
def pusher(monkeypatch, hass):
    """A PocasiPush wired to a recording session and allowed to send immediately."""
    session = _RecordingSession()
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz.anonymize", lambda d: d)

    pp = PocasiPush(hass, _make_entry())
    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)
    return pp, session


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------


async def test_ecowitt_is_posted_not_get(pusher) -> None:
    """Their server accepts the Ecowitt protocol only via POST."""
    pp, session = pusher
    await pp.push_data_to_server(ECOWITT_PAYLOAD, "ECOWITT")

    assert len(session.calls) == 1
    assert session.calls[0]["verb"] == "POST"


async def test_ecowitt_uses_its_own_endpoint(pusher) -> None:
    pp, session = pusher
    await pp.push_data_to_server(ECOWITT_PAYLOAD, "ECOWITT")

    assert session.calls[0]["url"] == f"{POCASI_CZ_URL}{POCASI_CZ_ECOWITT_URL}"
    assert session.calls[0]["url"] != f"{POCASI_CZ_URL}{DEFAULT_URL}"


async def test_credentials_go_in_the_query_string_as_id_and_pas(pusher) -> None:
    """`PAS`, not `PASS`/`PASSWORD` - the PWS spelling is rejected here."""
    pp, session = pusher
    await pp.push_data_to_server(ECOWITT_PAYLOAD, "ECOWITT")

    params = session.calls[0]["params"]
    assert params == {"ID": "myid", "PAS": "mykey"}
    assert "PASS" not in params
    assert "PASSWORD" not in params


async def test_station_payload_is_forwarded_verbatim(pusher) -> None:
    """A full forward: what the station sent is what the server receives."""
    pp, session = pusher
    await pp.push_data_to_server(ECOWITT_PAYLOAD, "ECOWITT")

    assert session.calls[0]["body"] == ECOWITT_PAYLOAD


async def test_credentials_are_not_injected_into_the_body(pusher) -> None:
    """Only the query string carries our credentials; the body stays the station's."""
    pp, session = pusher
    await pp.push_data_to_server(ECOWITT_PAYLOAD, "ECOWITT")

    body = session.calls[0]["body"]
    for key in ("ID", "PAS", "PASSWORD", "wsid", "wspw"):
        assert key not in body


async def test_ecowitt_post_is_bounded_by_a_timeout(pusher) -> None:
    """The POST is awaited inside the station's own request, so it must be bounded.

    Home Assistant's shared session sets no timeout, leaving aiohttp's 5 minute
    default - long past the point where the station gives up waiting for us.
    """
    from custom_components.sws12500.const import FORWARD_TIMEOUT

    pp, session = pusher
    await pp.push_data_to_server(ECOWITT_PAYLOAD, "ECOWITT")

    timeout = session.calls[0]["timeout"]
    assert timeout is not None
    assert timeout.total == FORWARD_TIMEOUT


async def test_caller_payload_is_not_mutated(pusher) -> None:
    """The same dict is handed to Windy and to the coordinator afterwards."""
    pp, _ = pusher
    original = dict(ECOWITT_PAYLOAD)

    await pp.push_data_to_server(ECOWITT_PAYLOAD, "ECOWITT")

    assert ECOWITT_PAYLOAD == original


# ---------------------------------------------------------------------------
# The PWS / WSLink modes keep their existing shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "path", "id_key", "pw_key"),
    [("WU", DEFAULT_URL, "ID", "PASSWORD"), ("WSLINK", "/data/upload.php", "wsid", "wspw")],
)
async def test_legacy_modes_still_use_get_with_inline_credentials(pusher, mode, path, id_key, pw_key) -> None:
    pp, session = pusher
    await pp.push_data_to_server({"tempf": "43.2"}, mode)

    call = session.calls[0]
    assert call["verb"] == "GET"
    assert call["url"] == f"{POCASI_CZ_URL}{path}"
    assert call["params"][id_key] == "myid"
    assert call["params"][pw_key] == "mykey"


# ---------------------------------------------------------------------------
# Shared behaviour still applies to the new mode
# ---------------------------------------------------------------------------


async def test_ecowitt_respects_the_send_interval(monkeypatch, hass) -> None:
    session = _RecordingSession()
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )
    pp = PocasiPush(hass, _make_entry())
    pp.next_update = dt_util.utcnow() + timedelta(seconds=999)

    await pp.push_data_to_server(ECOWITT_PAYLOAD, "ECOWITT")

    assert session.calls == []
    assert pp.last_status == "rate_limited_local"


@pytest.mark.parametrize("missing", ["api_id", "api_key"])
async def test_ecowitt_needs_credentials(monkeypatch, hass, missing) -> None:
    session = _RecordingSession()
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )
    pp = PocasiPush(hass, _make_entry(**{missing: ""}))
    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    await pp.push_data_to_server(ECOWITT_PAYLOAD, "ECOWITT")

    assert session.calls == []
    assert pp.last_status == "config_error"


async def test_ecowitt_auth_error_disables_forwarding(monkeypatch, hass) -> None:
    session = _RecordingSession(response=_FakeResponse(status=401))
    monkeypatch.setattr(
        "custom_components.sws12500.pocasti_cz.async_get_clientsession",
        lambda _h: session,
    )
    monkeypatch.setattr("custom_components.sws12500.pocasti_cz.anonymize", lambda d: d)

    entry = _make_entry()

    async def _apply(_hass, _entry, key, value):
        entry.options[key] = value
        return True

    monkeypatch.setattr("custom_components.sws12500.pocasti_cz.update_options", MagicMock(side_effect=_apply))

    pp = PocasiPush(hass, entry)
    pp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    await pp.push_data_to_server(ECOWITT_PAYLOAD, "ECOWITT")

    assert pp.last_status == "auth_error"
    assert pp.enabled is False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def test_pas_is_masked_for_logging() -> None:
    """`PAS` is a credential; the debug log must not print it."""
    from custom_components.sws12500.utils import anonymize

    assert anonymize({"ID": "myid", "PAS": "mykey"}) == {"ID": "***", "PAS": "***"}


# ---------------------------------------------------------------------------
# Windy takes the same payload translated to the field names it accepts
#
# Windy has no Ecowitt endpoint, so `baromrelin`, `dewpointf`, `tempinf`,
# `humidityin` and `hourlyrainin` would not be understood there.
# ---------------------------------------------------------------------------


def test_ecowitt_to_windy_renames_the_diverging_fields() -> None:
    from custom_components.sws12500.utils import remap_ecowitt_to_windy

    translated = remap_ecowitt_to_windy(ECOWITT_PAYLOAD)

    assert translated["dewptf"] == "20.3"
    assert translated["baromin"] == "28.792"
    assert translated["indoortempf"] == "53.4"
    assert translated["indoorhumidity"] == "76"
    assert translated["rainin"] == "2.08"  # WU `rainin` is the past hour

    # The Ecowitt spellings must be gone, not merely duplicated.
    for gone in ("baromrelin", "tempinf", "humidityin", "hourlyrainin", "dewpointf"):
        assert gone not in translated


def test_ecowitt_to_windy_keeps_the_shared_names() -> None:
    from custom_components.sws12500.utils import remap_ecowitt_to_windy

    translated = remap_ecowitt_to_windy(ECOWITT_PAYLOAD)

    for same in ("tempf", "humidity", "windspeedmph", "windgustmph", "winddir", "solarradiation", "dailyrainin"):
        assert translated[same] == ECOWITT_PAYLOAD[same]


def test_ecowitt_to_windy_drops_device_metadata() -> None:
    """Allowlist: station metadata has no meaning upstream and must not be forwarded."""
    from custom_components.sws12500.utils import remap_ecowitt_to_windy

    translated = remap_ecowitt_to_windy(ECOWITT_PAYLOAD)

    for junk in ("PASSKEY", "stationtype", "model", "freq", "baromabsin"):
        assert junk not in translated


def test_ecowitt_to_windy_ignores_unknown_future_fields() -> None:
    """A denylist would forward whatever a future firmware starts sending."""
    from custom_components.sws12500.utils import remap_ecowitt_to_windy

    translated = remap_ecowitt_to_windy({**ECOWITT_PAYLOAD, "some_new_sensor_v9": "42"})
    assert "some_new_sensor_v9" not in translated


def test_ecowitt_to_windy_handles_a_partial_payload() -> None:
    from custom_components.sws12500.utils import remap_ecowitt_to_windy

    assert remap_ecowitt_to_windy({"tempf": "43.2"}) == {"tempf": "43.2"}
    assert remap_ecowitt_to_windy({}) == {}


def test_ecowitt_to_windy_keeps_the_windy_uv_spelling() -> None:
    """Windy documents the UV index as lowercase `uv`; WU spells it `UV`.

    The WSLink converter already emits `uv` on the path that demonstrably works, so
    this table has to follow Windy rather than WU - otherwise Ecowitt users silently
    lose the UV index upstream. See `test_both_windy_converters_agree_on_uv`.
    """
    from custom_components.sws12500.utils import remap_ecowitt_to_windy

    translated = remap_ecowitt_to_windy(ECOWITT_PAYLOAD)
    assert translated["uv"] == "0"
    assert "UV" not in translated


def test_ecowitt_to_windy_produces_names_the_wu_pipeline_knows() -> None:
    """The translated names must be the ones a real PWS station sends.

    That is what makes the Windy forward work: it is the already-proven path, so the
    output is pinned against the integration's own WU parser rather than guessed. `uv`
    is the documented exception - Windy's own spelling, see the table's comment.
    """
    from custom_components.sws12500.const import REMAP_ITEMS
    from custom_components.sws12500.utils import remap_ecowitt_to_windy

    translated = remap_ecowitt_to_windy(ECOWITT_PAYLOAD)
    unknown = set(translated) - set(REMAP_ITEMS) - {"dateutc", "uv"}
    assert not unknown, f"field names neither protocol defines: {sorted(unknown)}"
