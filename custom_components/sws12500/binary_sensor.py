"""Binary sensor platform for SWS12500.

Exposes low-battery warnings and water-leak state as binary sensors; the raw value
that means `on` differs per family and comes from the entity description.
Auto-discovery adds entities without reloading the entry, using callbacks stored on `runtime_data`.
"""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .battery_sensors import WSBinarySensor
from .battery_sensors_def import WSLINK_BINARY_SENSORS
from .const import SENSORS_TO_LOAD
from .data import SWSConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: SWSConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the binary sensors (battery and water leak)."""

    del hass

    runtime = entry.runtime_data
    coordinator = runtime.coordinator

    # Persist platform callback + description map for dynamic entity creation.
    runtime.add_binary_entities = async_add_entities
    runtime.binary_descriptions = {desc.key: desc for desc in WSLINK_BINARY_SENSORS}
    runtime.added_binary_keys = set()

    # Initial entities for battery keys that station already reports.
    # `SENSORS_TO_LOAD` accumulates all discovered keys across runs.
    loaded = set(entry.options.get(SENSORS_TO_LOAD, []))
    entities: list[WSBinarySensor] = []
    for desc in WSLINK_BINARY_SENSORS:
        if desc.key in loaded:
            entities.append(WSBinarySensor(coordinator, desc))
            runtime.added_binary_keys.add(desc.key)

    if entities:
        async_add_entities(entities)


def add_new_binary_sensors(hass: HomeAssistant, entry: SWSConfigEntry, keys: list[str]) -> None:
    """Dynamic add newly discovered binary sensors without reloading the entry.

    Called from webhook handler in __init__.py.
    Safe no-op if the platform hasn't finished setting up yet (e.g. callback/description map missing).
    Duplicate keys are ignored (only keys with an entity description that haven't been added yet are added).
    """

    del hass  # kept for backwards-compatible call signature; not used after runtime_data migration

    runtime = getattr(entry, "runtime_data", None)
    if runtime is None:
        return
    add_entities = runtime.add_binary_entities
    if add_entities is None:
        return

    descriptions = runtime.binary_descriptions
    coordinator = runtime.coordinator
    added = runtime.added_binary_keys

    new_entities: list[BinarySensorEntity] = []
    for key in keys:
        if key in added:
            continue
        if (desc := descriptions.get(key)) is None:
            continue

        new_entities.append(WSBinarySensor(coordinator, desc))
        added.add(key)

    if new_entities:
        add_entities(new_entities)
