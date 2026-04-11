"""Binary sensor platform for SWS12500.

Exposes low-battery warnings as binary sensors.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from py_typecheck import checked

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .battery_sensors import BatteryBinarySensor
from .battery_sensors_def import BATTERY_BINARY_SENSORS
from .const import DOMAIN, SENSORS_TO_LOAD
from .data import ENTRY_ADD_BINARY_ENTITIES, ENTRY_ADDED_BINARY_KEYS, ENTRY_BINARY_DESCRIPTION, ENTRY_COORDINATOR

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up battery binary sensors."""

    if (hass_data := checked(hass.data.get(DOMAIN), dict[str, Any])) is None:
        return

    if (entry_data := checked(hass_data.get(entry.entry_id), dict[str, Any])) is None:
        return

    coordinator = entry_data.get(ENTRY_COORDINATOR)
    if coordinator is None:
        return

    # Save callback and descriptions for later auto-discovery.
    # webhook needs this to dynamicaly add entities withou reload

    description = {desc.key: desc for desc in BATTERY_BINARY_SENSORS}
    entry_data[ENTRY_ADD_BINARY_ENTITIES] = async_add_entities
    entry_data[ENTRY_BINARY_DESCRIPTION] = description

    added_keys: set[str] = set()
    entry_data[ENTRY_ADDED_BINARY_KEYS] = added_keys

    # Create binary sensors for battery key that station send.
    # SENSORS_TO_LOAD contains all discovered keys.

    loaded = set(entry.options.get(SENSORS_TO_LOAD, []))

    entities: list[BatteryBinarySensor] = []

    for desc in BATTERY_BINARY_SENSORS:
        if desc.key in loaded:
            entities.append(BatteryBinarySensor(coordinator, desc))
            added_keys.add(desc.key)

    if entities:
        async_add_entities(entities)


def add_new_binary_sensors(hass: HomeAssistant, entry: ConfigEntry, keys: list[str]) -> None:
    """Dynamic add newly discovered enetities.

    Called from webhook handler in __init__.py.
    """

    if (hass_data := checked(hass.data.get(DOMAIN), dict[str, Any])) is None:
        return

    if (entry_data := checked(hass_data.get(entry.entry_id), dict[str, Any])) is None:
        return

    add_entities = entry_data.get(ENTRY_ADD_BINARY_ENTITIES)
    description = entry_data.get(ENTRY_BINARY_DESCRIPTION)
    coordinator = entry_data.get(ENTRY_COORDINATOR)
    added_keys: set[str] | None = entry_data.get(ENTRY_ADDED_BINARY_KEYS)

    if add_entities is None or description is None or coordinator is None:
        return

    if added_keys is None:
        added_keys = set()
        entry_data[ENTRY_ADDED_BINARY_KEYS] = added_keys

    description_map = cast("dict[str, Any]", description)
    added = added_keys

    new_entities: list[BinarySensorEntity] = []
    for key in keys:
        if key in added:
            continue
        desc = description_map.get(key)
        if desc is None:
            continue
        new_entities.append(BatteryBinarySensor(coordinator, desc))
        added.add(key)

    if new_entities:
        add_fn = cast("AddEntitiesCallback", add_entities)
        add_fn(new_entities)
