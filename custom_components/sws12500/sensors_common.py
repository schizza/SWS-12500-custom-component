"""Common classes for sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntityDescription


@dataclass(frozen=True, kw_only=True)
class WeatherSensorEntityDescription(SensorEntityDescription):
    """Describe Weather Sensor entities."""

    value_fn: Callable[[Any], int | float | str | None] | None = None
    value_from_data_fn: Callable[[dict[str, Any]], int | float | str | None] | None = (
        None
    )
