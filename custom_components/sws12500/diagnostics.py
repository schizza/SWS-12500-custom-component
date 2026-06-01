"""Diagnostics support for the SWS12500 integration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.components.diagnostics import async_redact_data  # pyright: ignore[reportUnknownVariableType]
from homeassistant.core import HomeAssistant

from .const import API_ID, API_KEY, POCASI_CZ_API_ID, POCASI_CZ_API_KEY, WINDY_STATION_ID, WINDY_STATION_PW
from .data import SWSConfigEntry

TO_REDACT = {
    API_ID,
    API_KEY,
    POCASI_CZ_API_ID,
    POCASI_CZ_API_KEY,
    WINDY_STATION_ID,
    WINDY_STATION_PW,
    "ID",
    "PASSWORD",
    "wsid",
    "wspw",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: SWSConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    del hass  # Unused, but required by the interface

    runtime = entry.runtime_data
    health_data = runtime.health_data

    if health_data is None:
        # Fallback to the live coordinator snapshot if no payload has been persisted yet.
        health_data = runtime.health_coordinator.data

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": async_redact_data(dict(entry.options), TO_REDACT),
        "health_data": async_redact_data(
            deepcopy(health_data) if health_data else {},
            TO_REDACT,
        ),
    }
