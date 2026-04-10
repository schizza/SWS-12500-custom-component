"""Legacy definitions."""

from typing import Final

from py_typecheck import checked_or

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.issue_registry import IssueSeverity

from .const import DOMAIN, SENSORS_TO_LOAD

LEGACY_REMOVE_VERSION: Final = "2.1.0"
LEGACY_BATTERY_KEYS: Final[set[str]] = {
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


def _legacy_battery_issue_id(entry: ConfigEntry) -> str:
    """Issued id."""

    return f"legacy_battery_sensor_deprecation_{entry.entry_id}"


def _has_legacy_battery_loaded(entry: ConfigEntry) -> bool:
    loaded = set(checked_or(entry.options.get(SENSORS_TO_LOAD), list[str], []))
    return bool(loaded & LEGACY_BATTERY_KEYS)


def update_legacy_battery_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update legacy battery issue."""

    issue_id = _legacy_battery_issue_id(entry=entry)

    if _has_legacy_battery_loaded(entry=entry):
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id=issue_id,
            is_persistent=True,
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="legacy_battery_sensor_deprecated",
            translation_placeholders={"remove_version": LEGACY_REMOVE_VERSION},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id=issue_id)
