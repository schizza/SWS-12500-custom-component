"""Utils for SWS12500."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DEV_DBG, REMAP_ITEMS, SENSORS_TO_LOAD

_LOGGER = logging.getLogger(__name__)


async def update_options(
    hass: HomeAssistant, entry: ConfigEntry, update_key, update_value
) -> None:
    """Update config.options entry."""
    conf = {}

    for k in entry.options:
        conf[k] = entry.options[k]

    conf[update_key] = update_value

    return hass.config_entries.async_update_entry(entry, options=conf)


def anonymize(data):
    """Anoynimize recieved data."""

    anonym = {}
    for k in data:
        if k not in ("ID", "PASSWORD"):
            anonym[k] = data[k]

    return anonym


def remap_items(entities):
    """Remap items in query."""
    items = {}
    for item in entities:
        if item in REMAP_ITEMS:
            items[REMAP_ITEMS[item]] = entities[item]

    return items


def check_disabled(hass: HomeAssistant, items, config_entry: ConfigEntry) -> list | None:
    """Check if we have data for unloaded sensors.

    If so, then add sensor to load queue.

    Returns list of found sensors or None
    """

    log: bool = config_entry.options.get(DEV_DBG)
    entityFound: bool = False
    loaded_sensors: list = config_entry.options.get(SENSORS_TO_LOAD) if config_entry.options.get(SENSORS_TO_LOAD) else []

    for item in items:
        if log:
            _LOGGER.info("Checking %s", item)

        if item not in loaded_sensors:
            loaded_sensors.append(item)
            entityFound = True
            if log:
                _LOGGER.info("Add sensor (%s) to loading queue", item)

    return loaded_sensors if entityFound else None
