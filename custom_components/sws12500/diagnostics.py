"""Diagnostics support for the SWS12500 integration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from py_typecheck import checked, checked_or

from homeassistant.components.diagnostics import (
    async_redact_data,  # pyright: ignore[reportUnknownVariableType]
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    API_ID,
    API_KEY,
    DOMAIN,
    POCASI_CZ_API_ID,
    POCASI_CZ_API_KEY,
    WINDY_STATION_ID,
    WINDY_STATION_PW,
)
from .data import ENTRY_HEALTH_COORD, ENTRY_HEALTH_DATA

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


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    data = checked_or(hass.data.get(DOMAIN), dict[str, Any], {})

    if (entry_data := checked(data.get(entry.entry_id), dict[str, Any])) is None:
        entry_data = {}

    health_data = checked(entry_data.get(ENTRY_HEALTH_DATA), dict[str, Any])
    if health_data is None:
        coordinator = entry_data.get(ENTRY_HEALTH_COORD)
        health_data = getattr(coordinator, "data", None)

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": async_redact_data(dict(entry.options), TO_REDACT),
        "health_data": async_redact_data(
            deepcopy(health_data) if health_data else {},
            TO_REDACT,
        ),
    }
