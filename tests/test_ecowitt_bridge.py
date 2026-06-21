"""Tests for the Ecowitt bridge and native passthrough sensor.

Covers `custom_components.sws12500.ecowitt`:
- `EcowittBridge`: set_add_entities, process_payload, _on_new_sensor branches,
  and the `unmapped_sensor` / `all_sensors` properties.
- `EcoWittNativeSensor`: __init__ (mapped/unmapped stype, station / no station),
  native_value, async_added_to_hass / async_will_remove_from_hass and _handle_update.

The tests drive real `aioecowitt` parsing where practical and construct
`EcoWittSensor` objects directly to exercise deterministic branches.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from aioecowitt import EcoWittSensor, EcoWittSensorTypes
from aioecowitt.station import EcoWittStation
import pytest

from custom_components.sws12500.const import DOMAIN, REMAP_ECOWITT_COMPAT
from custom_components.sws12500.ecowitt import STYPE_TO_HA, EcowittBridge, EcoWittNativeSensor

# A realistic Ecowitt POST payload. `model` is required by aioecowitt's
# station extraction. Contains both internally mapped fields (tempf, humidity,
# windspeedmph, baromrelin, dewpointf) and unmapped fields (pm25_ch1, co2).
_PAYLOAD: dict[str, Any] = {
    "PASSKEY": "ABC123",
    "stationtype": "GW1000",
    "model": "GW1000",
    "dateutc": "2024-01-01 00:00:00",
    "freq": "868M",
    "tempf": "68.0",
    "humidity": "50",
    "windspeedmph": "1.0",
    "baromrelin": "29.9",
    "pm25_ch1": "12.0",
    "co2": "400",
}


def _make_bridge() -> EcowittBridge:
    """Build a bridge with lightweight hass / config stubs.

    The bridge only stores hass/config; parsing is delegated to aioecowitt.
    """
    hass = SimpleNamespace()
    config = SimpleNamespace(options={})
    return EcowittBridge(hass, config)


def _make_sensor(
    *,
    key: str = "pm25_ch1",
    name: str = "PM2.5 CH1",
    stype: EcoWittSensorTypes = EcoWittSensorTypes.PM25,
    station: EcoWittStation | None = None,
    value: Any = 12.0,
) -> EcoWittSensor:
    """Construct a real EcoWittSensor for entity-level tests."""
    if station is None:
        station = EcoWittStation(
            station="GW1000",
            model="GW1000",
            frequence="868M",
            key="ABC123",
        )
    sensor = EcoWittSensor(name, key, stype, station)
    sensor.value = value
    return sensor


# --------------------------------------------------------------------------- #
# EcowittBridge
# --------------------------------------------------------------------------- #


def test_bridge_init_registers_new_sensor_cb() -> None:
    """The bridge wires its own _on_new_sensor into the listener."""
    bridge = _make_bridge()
    assert bridge._on_new_sensor in bridge._listener.new_sensor_cb
    assert bridge._add_entities_cb is None


def test_set_add_entities_stores_callback() -> None:
    """set_add_entities stores the platform callback."""
    bridge = _make_bridge()
    cb = MagicMock()
    bridge.set_add_entities(cb)
    assert bridge._add_entities_cb is cb


@pytest.mark.asyncio
async def test_process_payload_returns_mapped_result() -> None:
    """process_payload parses payload and returns only internally mapped keys."""
    bridge = _make_bridge()

    result = await bridge.process_payload(dict(_PAYLOAD))

    # Mapped fields present in the payload are remapped to internal keys.
    assert result[REMAP_ECOWITT_COMPAT["tempf"]] == "68.0"
    assert result[REMAP_ECOWITT_COMPAT["humidity"]] == "50"
    assert result[REMAP_ECOWITT_COMPAT["windspeedmph"]] == "1.0"
    assert result[REMAP_ECOWITT_COMPAT["baromrelin"]] == "29.9"

    # Unmapped fields never appear in mapped_result.
    assert all(k in REMAP_ECOWITT_COMPAT.values() for k in result)

    # aioecowitt populated the listener with sensors.
    assert bridge.all_sensors
    assert "ABC123.tempf" in bridge.all_sensors


@pytest.mark.asyncio
async def test_process_payload_no_mapped_fields() -> None:
    """A payload without mapped fields yields an empty mapped_result."""
    bridge = _make_bridge()
    data = {
        "PASSKEY": "ABC123",
        "stationtype": "GW1000",
        "model": "GW1000",
        "dateutc": "2024-01-01 00:00:00",
        "co2": "400",
    }
    result = await bridge.process_payload(data)
    assert result == {}


@pytest.mark.asyncio
async def test_process_payload_creates_native_entities_for_unmapped() -> None:
    """With a callback set, unmapped sensors become native entities."""
    bridge = _make_bridge()
    created: list[EcoWittNativeSensor] = []
    bridge.set_add_entities(lambda entities: created.extend(entities))

    await bridge.process_payload(dict(_PAYLOAD))

    created_keys = {e._ecowitt_sensor.key for e in created}
    # Unmapped sensors got native entities ...
    assert "pm25_ch1" in created_keys
    assert "co2" in created_keys
    # ... but mapped sensors did NOT.
    assert "tempf" not in created_keys
    assert "humidity" not in created_keys
    assert all(isinstance(e, EcoWittNativeSensor) for e in created)


def test_on_new_sensor_skips_mapped_key() -> None:
    """A sensor whose key has an internal mapping creates no entity."""
    bridge = _make_bridge()
    bridge.set_add_entities(MagicMock())
    sensor = _make_sensor(key="tempf", stype=EcoWittSensorTypes.TEMPERATURE_F)

    bridge._on_new_sensor(sensor)

    bridge._add_entities_cb.assert_not_called()
    assert "tempf" not in bridge._know_native_keys


def test_on_new_sensor_skips_already_known() -> None:
    """A sensor whose key is already tracked creates no new entity."""
    bridge = _make_bridge()
    cb = MagicMock()
    bridge.set_add_entities(cb)
    bridge._know_native_keys.add("pm25_ch1")
    sensor = _make_sensor(key="pm25_ch1")

    bridge._on_new_sensor(sensor)

    cb.assert_not_called()


def test_on_new_sensor_no_callback_is_noop() -> None:
    """Without a platform callback the discovery is a no-op (not tracked)."""
    bridge = _make_bridge()
    sensor = _make_sensor(key="pm25_ch1")

    bridge._on_new_sensor(sensor)  # _add_entities_cb is None

    assert "pm25_ch1" not in bridge._know_native_keys


def test_on_new_sensor_creates_entity() -> None:
    """An unmapped, unknown sensor creates and registers a native entity."""
    bridge = _make_bridge()
    cb = MagicMock()
    bridge.set_add_entities(cb)
    sensor = _make_sensor(key="pm25_ch1")

    bridge._on_new_sensor(sensor)

    assert "pm25_ch1" in bridge._know_native_keys
    cb.assert_called_once()
    (entities,) = cb.call_args.args
    assert len(entities) == 1
    assert isinstance(entities[0], EcoWittNativeSensor)
    assert entities[0]._ecowitt_sensor is sensor


@pytest.mark.asyncio
async def test_unmapped_sensor_property() -> None:
    """unmapped_sensor returns only sensors without an internal mapping."""
    bridge = _make_bridge()
    await bridge.process_payload(dict(_PAYLOAD))

    unmapped = bridge.unmapped_sensor
    keys = {s.key for s in unmapped.values()}

    assert "pm25_ch1" in keys
    assert "co2" in keys
    # Mapped sensors are excluded.
    assert "tempf" not in keys
    assert "humidity" not in keys


@pytest.mark.asyncio
async def test_all_sensors_property() -> None:
    """all_sensors returns the listener's full sensor dict."""
    bridge = _make_bridge()
    await bridge.process_payload(dict(_PAYLOAD))

    assert bridge.all_sensors is bridge._listener.sensors
    assert "ABC123.tempf" in bridge.all_sensors
    assert "ABC123.pm25_ch1" in bridge.all_sensors


# --------------------------------------------------------------------------- #
# EcoWittNativeSensor
# --------------------------------------------------------------------------- #


def test_native_sensor_init_with_mapped_stype() -> None:
    """A known stype sets device class / unit / state class and device info."""
    station = EcoWittStation(
        station="GW1000", model="GW1000", frequence="868M", key="ABC123"
    )
    sensor = _make_sensor(key="pm25_ch1", stype=EcoWittSensorTypes.PM25, station=station)

    entity = EcoWittNativeSensor(sensor)

    assert entity._attr_unique_id == "ecowitt_pm25_ch1"
    assert entity._attr_name == "PM2.5 CH1"
    assert entity._attr_translation_key is None

    device_class, unit, state_class = STYPE_TO_HA[EcoWittSensorTypes.PM25]
    assert entity._attr_device_class == device_class
    assert entity._attr_native_unit_of_measurement == unit
    assert entity._attr_state_class == state_class

    # Device info groups the entity under the station device.
    info = entity._attr_device_info
    assert info["name"] == "Ecowitt GW1000"
    assert info["model"] == "GW1000"
    assert (DOMAIN, "ecowitt_ABC123") in info["identifiers"]
    assert info["manufacturer"] == "Ecowitt impl. from Schizza for SWS12500"


def test_native_sensor_init_with_unmapped_stype() -> None:
    """An unknown stype leaves device class / unit / state class unset.

    Device info is still attached (the recent change).
    """
    assert EcoWittSensorTypes.INTERNAL not in STYPE_TO_HA
    station = EcoWittStation(
        station="GW1000", model="GW1000", frequence="868M", key="ABC123"
    )
    sensor = _make_sensor(
        key="runtime",
        name="Runtime",
        stype=EcoWittSensorTypes.INTERNAL,
        station=station,
        value="1000",
    )

    entity = EcoWittNativeSensor(sensor)

    # No HA metadata set for unknown types.
    assert getattr(entity, "_attr_device_class", None) is None
    assert getattr(entity, "_attr_native_unit_of_measurement", None) is None
    assert getattr(entity, "_attr_state_class", None) is None

    # Device info is still present.
    info = entity._attr_device_info
    assert info["name"] == "Ecowitt GW1000"
    assert (DOMAIN, "ecowitt_ABC123") in info["identifiers"]


def test_native_sensor_init_without_station() -> None:
    """A sensor with no station falls back to generic device info."""
    sensor = _make_sensor(key="pm25_ch1", stype=EcoWittSensorTypes.PM25)
    # Force the no-station branch.
    sensor.station = None  # type: ignore[assignment]

    entity = EcoWittNativeSensor(sensor)

    info = entity._attr_device_info
    assert info["name"] == "Ecowitt station"
    assert info["model"] is None
    assert (DOMAIN, "ecowitt") in info["identifiers"]


def test_native_value_returns_value() -> None:
    """native_value returns the underlying sensor value."""
    sensor = _make_sensor(value=42.0)
    entity = EcoWittNativeSensor(sensor)
    assert entity.native_value == 42.0


@pytest.mark.parametrize("empty", [None, ""])
def test_native_value_none_or_empty(empty: Any) -> None:
    """native_value maps None and "" to None."""
    sensor = _make_sensor(value=empty)
    entity = EcoWittNativeSensor(sensor)
    assert entity.native_value is None


@pytest.mark.asyncio
async def test_added_and_removed_callback_lifecycle() -> None:
    """async_added/async_will_remove register and unregister the update cb."""
    sensor = _make_sensor()
    entity = EcoWittNativeSensor(sensor)

    assert entity._handle_update not in sensor.update_cb

    await entity.async_added_to_hass()
    assert entity._handle_update in sensor.update_cb

    await entity.async_will_remove_from_hass()
    assert entity._handle_update not in sensor.update_cb


@pytest.mark.asyncio
async def test_will_remove_when_callback_absent() -> None:
    """async_will_remove is safe when the callback was never registered."""
    sensor = _make_sensor()
    entity = EcoWittNativeSensor(sensor)

    # Not added; removal must not raise and must not touch the list.
    assert entity._handle_update not in sensor.update_cb
    await entity.async_will_remove_from_hass()
    assert entity._handle_update not in sensor.update_cb


def test_handle_update_writes_ha_state() -> None:
    """_handle_update forwards to async_write_ha_state."""
    sensor = _make_sensor()
    entity = EcoWittNativeSensor(sensor)
    entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]

    entity._handle_update()

    entity.async_write_ha_state.assert_called_once_with()
