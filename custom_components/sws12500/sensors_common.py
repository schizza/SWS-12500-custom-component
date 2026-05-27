"""Common classes for sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dev.custom_components.sws12500.const import VOCLevel
from homeassistant.components.sensor import SensorEntityDescription


@dataclass(frozen=True, kw_only=True)
class WeatherSensorEntityDescription(SensorEntityDescription):
    """Describe Weather Sensor entities."""

    value_fn: Callable[[Any], int | float | str | VOCLevel | None] | None = None
    value_from_data_fn: Callable[[dict[str, Any]], int | float | str | VOCLevel | None] | None = None

    deprecated: bool = False
    replacement_entity_domain: str | None = None
    replacement_entity_key: str | None = None
