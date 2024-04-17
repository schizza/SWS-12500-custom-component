"""Utils for SWS12500."""

import logging

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from .const import DEV_DBG, REMAP_ITEMS, SENSORS_TO_LOAD

_LOGGER = logging.getLogger(__name__)

async def translations(
    hass: HomeAssistant,
    translation_domain: str,
    translation_key: str,
    *,
    key: str = "message",
    category: str = "notify"
) -> str:
    """Get translated keys for domain."""

    localize_key = f"component.{translation_domain}.{category}.{translation_key}.{key}"

    language = hass.config.language

    _translations = await async_get_translations(
        hass, language, category, [translation_domain]
    )
    if localize_key in _translations:
        return _translations[localize_key]

async def translated_notification(
    hass: HomeAssistant,
    translation_domain: str,
    translation_key: str,
    translation_placeholders: dict[str, str] | None = None,
    notification_id: str | None = None,
    *,
    key: str = "message",
    category: str = "notify"
) -> str:
    """Translate notification."""

    localize_key = f"component.{translation_domain}.{category}.{translation_key}.{key}"

    localize_title = f"component.{translation_domain}.{category}.{translation_key}.title"

    language = hass.config.language

    _translations = await async_get_translations(
        hass, language, category, [translation_domain]
    )
    if localize_key in _translations:
        if not translation_placeholders:
            persistent_notification.async_create(
                hass,
                _translations[localize_key],
                _translations[localize_title],
                notification_id,
            )
        else:
            message = _translations[localize_key].format(**translation_placeholders)
            persistent_notification.async_create(
                hass, message, _translations[localize_title], notification_id
            )


async def update_options(
    hass: HomeAssistant, entry: ConfigEntry, update_key, update_value
) -> None:
    """Update config.options entry."""
    conf = {**entry.options}
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

def loaded_sensors(config_entry: ConfigEntry) -> list | None:
    """Get loaded sensors."""

    return config_entry.options.get(SENSORS_TO_LOAD) if config_entry.options.get(SENSORS_TO_LOAD) else []

def check_disabled(
    hass: HomeAssistant, items, config_entry: ConfigEntry
) -> list | None:
    """Check if we have data for unloaded sensors.

    If so, then add sensor to load queue.

    Returns list of found sensors or None
    """

    log: bool = config_entry.options.get(DEV_DBG)
    entityFound: bool = False
    _loaded_sensors = loaded_sensors(config_entry)
    missing_sensors: list = []

    for item in items:
        if log:
            _LOGGER.info("Checking %s", item)

        if item not in _loaded_sensors:
            missing_sensors.append(item)
            entityFound = True
            if log:
                _LOGGER.info("Add sensor (%s) to loading queue", item)

    return missing_sensors if entityFound else None
