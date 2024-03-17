"""Utils for SWS12500."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry
from homeassistant.SensorEntity import async_get as se

from .const import DISABLED_BY_DEFAULT, DOMAIN, REMAP_ITEMS

_LOGGER = logging.getLogger(__name__)


def update_options(
    hass: HomeAssistant, entry: ConfigEntry, update_key, update_value
) -> None:
    """Update config.options entry."""
    conf = {}

    for k in entry.options:
        conf[k] = entry.options[k]

    conf[update_key] = update_value

    hass.config_entries.async_update_entry(entry, options=conf)


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


async def check_disabled(hass: HomeAssistant, items, log: bool = False):
    """Check if we have data for disabed sensors.

    If so, then enable senosor.

    Returns True if sensor found else False
    """

    _ER = entity_registry.async_get(hass)
    _SE = se(hass)

    eid: str = None
    entityFound: bool = False

    for disabled in DISABLED_BY_DEFAULT:
        if log:
            _LOGGER.info("Checking %s", disabled)

        if disabled in items:
            eid = _ER.async_get_entity_id(Platform.SENSOR, DOMAIN, disabled)
            is_disabled = _ER.entities[eid].hidden

            if log:
                _LOGGER.info("Found sensor %s", eid)

            if is_disabled:
                if log:
                    _LOGGER.info("Sensor %s is hidden. Making visible", eid)
                _ER.async_update_entity(eid, hidden_by=None)
                entityFound = True

            elif not is_disabled and log:
                    _LOGGER.info("Sensor %s is visible.", eid)

    return entityFound
