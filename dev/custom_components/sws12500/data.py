"""Shared keys and helpers for storing integration runtime state in hass.data.

This integration uses `hass.data[DOMAIN][entry_id]` as a per-entry dictionary.
Keeping keys in one place prevents subtle bugs where different modules
store different value types under the same key.
"""

from __future__ import annotations

from typing import Final


# Per-entry dict keys stored under hass.data[DOMAIN][entry_id]
ENTRY_COORDINATOR: Final[str] = "coordinator"
ENTRY_ADD_ENTITIES: Final[str] = "async_add_entities"
ENTRY_DESCRIPTIONS: Final[str] = "sensor_descriptions"
ENTRY_LAST_OPTIONS: Final[str] = "last_options"
