"""Common classes for sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.sensor import SensorEntityDescription

from .const import VOCLevel


@dataclass(frozen=True, kw_only=True)
class WeatherSensorEntityDescription(SensorEntityDescription):
    """Describe Weather Sensor entities."""

    value_fn: Callable[[Any], int | float | str | VOCLevel | None] | None = None
    value_from_data_fn: Callable[[dict[str, Any]], int | float | str | VOCLevel | None] | None = None

    deprecated: bool = False
    replacement_entity_domain: str | None = None
    replacement_entity_key: str | None = None


@dataclass(frozen=True, kw_only=True)
class WSBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe a WSLink binary sensor.

    `on_value` is the raw payload value that means `on`, because the station's
    conventions differ per family and so do Home Assistant's:

    - a battery reports ``0`` for low, and ``BinarySensorDeviceClass.BATTERY``
      defines ``on`` as "low"
    - a water leak sensor reports ``1`` for a leak, and
      ``BinarySensorDeviceClass.MOISTURE`` defines ``on`` as "wet"

    Keeping it in the description means one entity class serves both instead of
    two near-identical ones that differ only in a comparison.
    """

    on_value: int
