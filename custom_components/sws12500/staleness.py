"""Stale sensor detection.

If a sensor key is in SENSORS_TO_LOAD but its station never reported it (or stopped reporting it
for an extended period), the corresponding HA entity becomes Unavailable indefinitely.

This module raises a Repairs issue listing such stale keys so users can decide whether to remove them.

Warmup avoids false-positives at integration startup before any payload arrives.
The check is in-memory only — restart/reload resets last_seen, but the 1h warmup covers re-population
from incoming webhooks.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.issue_registry import IssueSeverity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SENSORS_TO_LOAD
from .data import SWSConfigEntry

STALE_THRESHOLD: Final = timedelta(hours=24)
WARMUP_PERIOD: Final = timedelta(hours=1)


def _stale_sensor_issue_id(entry: SWSConfigEntry) -> str:
    """Return Repairs issue id for this config entry."""
    return f"stale_sensors_{entry.entry_id}"


@callback
def _find_stale_keys(entry: SWSConfigEntry) -> list[str]:
    """Return keys in SENSORS_TO_LOAD that haven't been seen recently."""
    runtime = entry.runtime_data
    now = dt_util.utcnow()

    if (now - runtime.started_at) < WARMUP_PERIOD:
        return []

    loaded = entry.options.get(SENSORS_TO_LOAD, [])
    last_seen = runtime.last_seen

    stale: list[str] = []
    for key in loaded:
        seen_at = last_seen.get(key)
        if seen_at is None or (now - seen_at) > STALE_THRESHOLD:
            stale.append(key)
    return stale


@callback
def update_stale_sensors_issue(hass: HomeAssistant, entry: SWSConfigEntry) -> None:
    """Create or clear a Repairs issue for stale sensor keys."""

    issue_id = _stale_sensor_issue_id(entry)
    stale = _find_stale_keys(entry)

    if stale:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id=issue_id,
            is_persistent=True,
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="stale_sensors_detected",
            translation_placeholders={
                "sensors": ", ".join(sorted(stale)),
            },
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id=issue_id)
