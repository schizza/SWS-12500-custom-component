"""Protocol conflict handling.

The legacy (PWS/WSLink) and Ecowitt endpoints both remap their payloads onto the *same*
internal sensor keys (`REMAP_ITEMS` / `REMAP_WSLINK_ITEMS` vs `REMAP_ECOWITT_COMPAT`) and
push them through the same coordinator. Running both at once is therefore unsound:

1. Units clash. The entity descriptions are chosen by the WSLink flag alone, so Ecowitt's
   imperial payload (`tempf`, `baromrelin`, `windspeedmph`, ...) is rendered with the
   WSLink set's metric units - 18 of the 26 Ecowitt-mapped keys disagree.
2. Payloads blank each other. `async_set_updated_data` *replaces* the coordinator payload,
   so every Ecowitt push blanks the keys only the legacy protocol reports (and vice versa),
   flipping those entities to `unknown` on every other push.
3. One entity, two sources. A single `sensor.outside_temp` would alternate between whatever
   the two endpoints report.

The initial config flow already keeps them exclusive (the `pws` step disables Ecowitt, the
`ecowitt` step disables legacy); only the options flow could turn both on. This module is
the single place that states the rule, so the config flow, the route wiring and the device
model all agree on it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from py_typecheck import checked_or

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.issue_registry import IssueSeverity

from .const import DOMAIN, ECOWITT_ENABLED, LEGACY_ENABLED

if TYPE_CHECKING:
    # Type-only: `data` imports `effective_protocols` from here at runtime, so a
    # runtime import back into `data` would close an import cycle.
    from .data import SWSConfigEntry

# Shown in the config/options flow when a submit would enable both protocols.
ERROR_MUTUALLY_EXCLUSIVE: Final = "protocols_mutually_exclusive"


@callback
def protocols_conflict(entry: SWSConfigEntry) -> bool:
    """Return whether this entry has both protocols enabled."""
    return checked_or(entry.options.get(LEGACY_ENABLED), bool, True) and checked_or(
        entry.options.get(ECOWITT_ENABLED), bool, False
    )


@callback
def effective_protocols(entry: SWSConfigEntry) -> tuple[bool, bool]:
    """Return the `(legacy, ecowitt)` state to actually wire up.

    Options written before this rule existed may still have both flags set. Rather than
    ingesting two protocols into one entity namespace, legacy wins - matching the
    precedence already documented in `health_coordinator._configured_protocol` - and
    `update_protocol_conflict_issue` tells the user what happened.
    """
    legacy = checked_or(entry.options.get(LEGACY_ENABLED), bool, True)
    ecowitt = checked_or(entry.options.get(ECOWITT_ENABLED), bool, False)

    if legacy and ecowitt:
        return True, False
    return legacy, ecowitt


def _issue_id(entry: SWSConfigEntry) -> str:
    """Return the Repairs issue id for this config entry."""
    return f"protocol_conflict_{entry.entry_id}"


@callback
def update_protocol_conflict_issue(hass: HomeAssistant, entry: SWSConfigEntry) -> None:
    """Create or clear the Repairs issue for a legacy/Ecowitt conflict."""

    issue_id = _issue_id(entry)

    if protocols_conflict(entry):
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id=issue_id,
            is_persistent=True,
            is_fixable=False,
            severity=IssueSeverity.ERROR,
            translation_key="protocol_conflict",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id=issue_id)
