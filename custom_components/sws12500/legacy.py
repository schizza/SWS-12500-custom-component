"""Legacy battery sensor deprecation.

The integration used to expose battery state as regular SensorEntity instance
(unique_id == bettery key), they have been migrated to BinarySensorEntity (uniqui_id == `key`_binary). Old entity-registry entries from
pre-migration installs orphan. This module raises a Repairs issue so user can celan them up.
"""

from __future__ import annotations

from typing import Final

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.helpers.issue_registry import IssueSeverity

from .const import DOMAIN
from .data import SWSConfigEntry

LEGACY_REMOVE_VERSION: Final = "2.1.0"
LEGACY_BATTERY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "outside_battery",
        "indoor_battery",
        "ch2_battery",
        "ch3_battery",
        "ch4_battery",
        "ch5_battery",
        "ch6_battery",
        "ch7_battery",
        "ch8_battery",
    }
)


def _legacy_battery_issue_id(entry: SWSConfigEntry) -> str:
    """Return Repairs issue id fpr this config entry."""
    return f"legacy_battery_sensor_deprecation_{entry.entry_id}"


@callback
def _orphan_legacy_battery_etries(hass: HomeAssistant, entry: SWSConfigEntry) -> list[str]:
    """Return entity_ids of legacy battery sensors still present in entity registry.

    Old non-binary battery entities have:
    - domian == "sensor"
    - unique_id matches a LEGACY_BATTERY_KESY entry (without `_binary` suffix)
    """
    ent_reg = er.async_get(hass)
    return [
        ent.entity_id
        for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if ent.domain == "sensor" and ent.unique_id in LEGACY_BATTERY_KEYS
    ]


@callback
def update_legacy_battery_issue(hass: HomeAssistant, entry: SWSConfigEntry) -> None:
    """Create or clear a Repairs issue for orphan legacy battery snesors."""

    issue_id = _legacy_battery_issue_id(entry=entry)
    orphans = _orphan_legacy_battery_etries(hass, entry)

    if orphans:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id=issue_id,
            is_persistent=True,
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="legacy_battery_sensor_deprecated",
            translation_placeholders={
                "remove_version": LEGACY_REMOVE_VERSION,
                "entities": ", ".join(orphans),
            },
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id=issue_id)
