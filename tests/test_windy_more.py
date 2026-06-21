"""Additional Windy branch coverage: duplicate (409), rate limit (429), 3-strike disable."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sws12500.const import WINDY_ENABLED, WINDY_LOGGER_ENABLED, WINDY_STATION_ID, WINDY_STATION_PW
from custom_components.sws12500.windy_func import WindyDuplicatePayloadDetected, WindyPush, WindyRateLimitExceeded
from homeassistant.util import dt as dt_util


@dataclass(slots=True)
class _FakeResponse:
    status: int

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def get(self, url: str, *, params=None, headers=None):
        return self._response


@pytest.fixture
def hass():
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


def test_verify_response_duplicate_raises(hass):
    wp = WindyPush(hass, _make_entry())
    with pytest.raises(WindyDuplicatePayloadDetected):
        wp.verify_windy_response(_FakeResponse(status=409))


def test_verify_response_rate_limit_raises(hass):
    wp = WindyPush(hass, _make_entry())
    with pytest.raises(WindyRateLimitExceeded):
        wp.verify_windy_response(_FakeResponse(status=429))


@pytest.mark.asyncio
async def test_push_duplicate_payload_sets_status_and_counts(monkeypatch, hass):
    wp = WindyPush(hass, _make_entry())
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: _FakeSession(_FakeResponse(status=409)),
    )

    ok = await wp.push_data_to_windy({"a": "b"})
    assert ok is True
    assert wp.last_status == "duplicate"
    assert wp.invalid_response_count == 1


@pytest.mark.asyncio
async def test_push_rate_limited_pauses_five_minutes(monkeypatch, hass):
    wp = WindyPush(hass, _make_entry())
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: _FakeSession(_FakeResponse(status=429)),
    )

    before = dt_util.utcnow()
    ok = await wp.push_data_to_windy({"a": "b"})
    assert ok is True
    assert wp.last_status == "rate_limited_remote"
    # next_update pushed ~5 minutes out by the rate-limit handler.
    assert wp.next_update > before + timedelta(minutes=4)


@pytest.mark.asyncio
async def test_push_duplicate_third_strike_disables(monkeypatch, hass):
    wp = WindyPush(hass, _make_entry())
    wp.invalid_response_count = 2  # next duplicate makes it 3 -> finally disables
    wp.next_update = dt_util.utcnow() - timedelta(seconds=1)

    update_options = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.update_options", update_options
    )
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.persistent_notification.create",
        MagicMock(),
    )
    monkeypatch.setattr(
        "custom_components.sws12500.windy_func.async_get_clientsession",
        lambda _h: _FakeSession(_FakeResponse(status=409)),
    )

    ok = await wp.push_data_to_windy({"a": "b"})
    assert ok is True
    assert wp.invalid_response_count == 3
    update_options.assert_awaited_once_with(hass, wp.config, WINDY_ENABLED, False)
