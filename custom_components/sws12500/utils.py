"""Utils for SWS12500."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import REMAP_ITEMS


def update_options(
    hass: HomeAssistant, entry: ConfigEntry, update_key, update_value
) -> None:
    """Update config.options entry."""
    conf = {}

    for k in entry.options:
        conf[k] = entry.options[k]

    conf[update_key] = update_value

    hass.config_entries.async_update_entry(entry, options=conf)


def remap_items(entities):
    """Remap items in query."""
    items = {}
    for item in entities:
        if item in REMAP_ITEMS:
            items[REMAP_ITEMS[item]] = entities[item]

    return items
