"""Tests for the SWS12500 config entry diagnostics.

These cover both branches of `async_get_config_entry_diagnostics`:
- `runtime_data.health_data` is populated and returned directly.
- `runtime_data.health_data` is None, so it falls back to the live
  `health_coordinator.data` snapshot.

In both cases secret keys listed in `TO_REDACT` must be replaced by the
Home Assistant `async_redact_data` sentinel, while non-secret values pass
through untouched.
"""

from __future__ import annotations

from types import SimpleNamespace

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sws12500.const import (
    API_ID,
    API_KEY,
    DOMAIN,
    POCASI_CZ_API_ID,
    POCASI_CZ_API_KEY,
    WINDY_STATION_ID,
    WINDY_STATION_PW,
)
from custom_components.sws12500.data import SWSRuntimeData
from custom_components.sws12500.diagnostics import async_get_config_entry_diagnostics

REDACTED = "**REDACTED**"


def _make_runtime(*, health_data, health_coordinator) -> SWSRuntimeData:
    """Build a runtime data container with lightweight stub coordinators.

    Diagnostics only ever reads `health_data` and `health_coordinator.data`,
    so the real coordinators can be replaced with plain stubs.
    """
    return SWSRuntimeData(
        coordinator=object(),  # type: ignore[arg-type]
        health_coordinator=health_coordinator,  # type: ignore[arg-type]
        last_options={},
        health_data=health_data,
    )


async def test_diagnostics_uses_persisted_health_data(hass) -> None:
    """When `health_data` is present it is returned and secrets are redacted."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            API_ID: "secret-api-id",
            API_KEY: "secret-api-key",
            "name": "Station",
        },
        options={
            WINDY_STATION_ID: "secret-windy-id",
            WINDY_STATION_PW: "secret-windy-pw",
            "interval": 60,
        },
    )
    entry.add_to_hass(hass)

    health_data = {
        "ID": "secret-station-id",
        "PASSWORD": "secret-station-pw",
        POCASI_CZ_API_ID: "secret-pocasi-id",
        POCASI_CZ_API_KEY: "secret-pocasi-key",
        "wsid": "secret-wsid",
        "wspw": "secret-wspw",
        "status": "ok",
    }
    # A separate coordinator snapshot that must NOT be used in this branch.
    health_coordinator = SimpleNamespace(data={"status": "stale-should-not-appear"})

    entry.runtime_data = _make_runtime(
        health_data=health_data,
        health_coordinator=health_coordinator,
    )

    result = await async_get_config_entry_diagnostics(hass, entry)

    # entry_data: secrets redacted, plain value preserved.
    assert result["entry_data"][API_ID] == REDACTED
    assert result["entry_data"][API_KEY] == REDACTED
    assert result["entry_data"]["name"] == "Station"

    # entry_options: secrets redacted, plain value preserved.
    assert result["entry_options"][WINDY_STATION_ID] == REDACTED
    assert result["entry_options"][WINDY_STATION_PW] == REDACTED
    assert result["entry_options"]["interval"] == 60

    # health_data: the persisted payload is used (not the coordinator snapshot).
    assert result["health_data"]["status"] == "ok"
    assert result["health_data"]["ID"] == REDACTED
    assert result["health_data"]["PASSWORD"] == REDACTED
    assert result["health_data"][POCASI_CZ_API_ID] == REDACTED
    assert result["health_data"][POCASI_CZ_API_KEY] == REDACTED
    assert result["health_data"]["wsid"] == REDACTED
    assert result["health_data"]["wspw"] == REDACTED

    # The original payload must be untouched (deepcopy is used internally).
    assert health_data["ID"] == "secret-station-id"


async def test_diagnostics_falls_back_to_coordinator_data(hass) -> None:
    """When `health_data` is None it falls back to the coordinator snapshot."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={API_ID: "secret-api-id", "name": "Station"},
        options={},
    )
    entry.add_to_hass(hass)

    coordinator_data = {
        "ID": "secret-station-id",
        "PASSWORD": "secret-station-pw",
        "status": "live",
    }
    health_coordinator = SimpleNamespace(data=coordinator_data)

    entry.runtime_data = _make_runtime(
        health_data=None,
        health_coordinator=health_coordinator,
    )

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry_data"][API_ID] == REDACTED
    assert result["entry_data"]["name"] == "Station"
    assert result["entry_options"] == {}

    # Fallback snapshot is used and redacted.
    assert result["health_data"]["status"] == "live"
    assert result["health_data"]["ID"] == REDACTED
    assert result["health_data"]["PASSWORD"] == REDACTED


async def test_diagnostics_empty_health_data(hass) -> None:
    """A falsy fallback snapshot yields an empty health_data dict."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    health_coordinator = SimpleNamespace(data=None)
    entry.runtime_data = _make_runtime(
        health_data=None,
        health_coordinator=health_coordinator,
    )

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["health_data"] == {}
    assert result["entry_data"] == {}
    assert result["entry_options"] == {}
