from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sws12500.const import (
    DEV_DBG,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    REMAP_ITEMS,
    REMAP_WSLINK_ITEMS,
    SENSORS_TO_LOAD,
    WIND_SPEED,
    UnitOfBat,
)
from custom_components.sws12500.utils import (
    anonymize,
    battery_level,
    battery_level_to_icon,
    celsius_to_fahrenheit,
    check_disabled,
    chill_index,
    fahrenheit_to_celsius,
    heat_index,
    loaded_sensors,
    remap_items,
    remap_wslink_items,
    translated_notification,
    translations,
    update_options,
    wind_dir_to_text,
)


@dataclass(slots=True)
class _EntryStub:
    entry_id: str = "test_entry_id"
    options: dict[str, Any] = None  # type: ignore[assignment]


class _ConfigEntriesStub:
    def __init__(self) -> None:
        self.async_update_entry = MagicMock(return_value=True)


class _HassStub:
    def __init__(self, language: str = "en") -> None:
        self.config = SimpleNamespace(language=language)
        self.config_entries = _ConfigEntriesStub()


@pytest.fixture
def hass() -> _HassStub:
    return _HassStub(language="en")


@pytest.fixture
def entry() -> _EntryStub:
    return _EntryStub(options={})


def test_anonymize_masks_secrets_and_keeps_other_values():
    data = {
        "ID": "abc",
        "PASSWORD": "secret",
        "wsid": "id2",
        "wspw": "pw2",
        "temp": 10,
        "ok": True,
    }
    out = anonymize(data)
    assert out["ID"] == "***"
    assert out["PASSWORD"] == "***"
    assert out["wsid"] == "***"
    assert out["wspw"] == "***"
    assert out["temp"] == 10
    assert out["ok"] is True


def test_remap_items_filters_unknown_keys():
    # Pick a known legacy key from the mapping
    legacy_key = next(iter(REMAP_ITEMS.keys()))
    internal_key = REMAP_ITEMS[legacy_key]

    entities = {legacy_key: "1", "unknown": "2"}
    out = remap_items(entities)

    assert out == {internal_key: "1"}


def test_remap_wslink_items_filters_unknown_keys():
    wslink_key = next(iter(REMAP_WSLINK_ITEMS.keys()))
    internal_key = REMAP_WSLINK_ITEMS[wslink_key]

    entities = {wslink_key: "x", "unknown": "y"}
    out = remap_wslink_items(entities)

    assert out == {internal_key: "x"}


def test_loaded_sensors_returns_list_or_empty(entry: _EntryStub):
    entry.options[SENSORS_TO_LOAD] = ["a", "b"]
    assert loaded_sensors(entry) == ["a", "b"]

    entry.options[SENSORS_TO_LOAD] = []
    assert loaded_sensors(entry) == []

    entry.options.pop(SENSORS_TO_LOAD)
    assert loaded_sensors(entry) == []


def test_check_disabled_returns_none_when_all_present(entry: _EntryStub):
    entry.options[SENSORS_TO_LOAD] = ["a", "b"]
    entry.options[DEV_DBG] = False

    missing = check_disabled({"a": "1", "b": "2"}, entry)
    assert missing is None


def test_check_disabled_returns_missing_keys(entry: _EntryStub):
    entry.options[SENSORS_TO_LOAD] = ["a"]
    entry.options[DEV_DBG] = False

    missing = check_disabled({"a": "1", "b": "2", "c": "3"}, entry)
    assert missing == ["b", "c"]


def test_check_disabled_logs_when_dev_dbg_enabled(entry: _EntryStub, monkeypatch):
    # Just ensure logging branches are exercised without asserting exact messages.
    entry.options[SENSORS_TO_LOAD] = []
    entry.options[DEV_DBG] = True

    monkeypatch.setattr(
        "custom_components.sws12500.utils._LOGGER.info", lambda *a, **k: None
    )

    missing = check_disabled({"a": "1"}, entry)
    assert missing == ["a"]


@pytest.mark.asyncio
async def test_update_options_calls_async_update_entry(
    hass: _HassStub, entry: _EntryStub
):
    entry.options = {"x": 1}
    ok = await update_options(hass, entry, "y", True)
    assert ok is True
    hass.config_entries.async_update_entry.assert_called_once()
    _called_entry = hass.config_entries.async_update_entry.call_args.args[0]
    assert _called_entry is entry
    called_options = hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert called_options["x"] == 1
    assert called_options["y"] is True


@pytest.mark.asyncio
async def test_translations_returns_value_when_key_present(
    hass: _HassStub, monkeypatch
):
    # Build the key that translations() will look for
    localize_key = "component.sws12500.entity.sensor.test.name"
    get_translations = AsyncMock(return_value={localize_key: "Translated"})
    monkeypatch.setattr(
        "custom_components.sws12500.utils.async_get_translations", get_translations
    )

    out = await translations(
        hass,
        "sws12500",
        "sensor.test",
        key="name",
        category="entity",
    )
    assert out == "Translated"


@pytest.mark.asyncio
async def test_translations_returns_none_when_key_missing(hass: _HassStub, monkeypatch):
    get_translations = AsyncMock(return_value={})
    monkeypatch.setattr(
        "custom_components.sws12500.utils.async_get_translations", get_translations
    )

    out = await translations(hass, "sws12500", "missing")
    assert out is None


@pytest.mark.asyncio
async def test_translated_notification_creates_notification_without_placeholders(
    hass: _HassStub, monkeypatch
):
    base_key = "component.sws12500.notify.added.message"
    title_key = "component.sws12500.notify.added.title"
    get_translations = AsyncMock(return_value={base_key: "Msg", title_key: "Title"})
    monkeypatch.setattr(
        "custom_components.sws12500.utils.async_get_translations", get_translations
    )

    create = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.utils.persistent_notification.async_create", create
    )

    await translated_notification(hass, "sws12500", "added")
    create.assert_called_once()
    args = create.call_args.args
    assert args[0] is hass
    assert args[1] == "Msg"
    assert args[2] == "Title"


@pytest.mark.asyncio
async def test_translated_notification_formats_placeholders(
    hass: _HassStub, monkeypatch
):
    base_key = "component.sws12500.notify.added.message"
    title_key = "component.sws12500.notify.added.title"
    get_translations = AsyncMock(
        return_value={base_key: "Hello {name}", title_key: "Title"}
    )
    monkeypatch.setattr(
        "custom_components.sws12500.utils.async_get_translations", get_translations
    )

    create = MagicMock()
    monkeypatch.setattr(
        "custom_components.sws12500.utils.persistent_notification.async_create", create
    )

    await translated_notification(
        hass, "sws12500", "added", translation_placeholders={"name": "World"}
    )
    create.assert_called_once()
    assert create.call_args.args[1] == "Hello World"


def test_battery_level_handles_none_empty_invalid_and_known_values():
    assert battery_level(None) == UnitOfBat.UNKNOWN
    assert battery_level("") == UnitOfBat.UNKNOWN
    assert battery_level("x") == UnitOfBat.UNKNOWN

    assert battery_level(0) == UnitOfBat.LOW
    assert battery_level("0") == UnitOfBat.LOW
    assert battery_level(1) == UnitOfBat.NORMAL
    assert battery_level("1") == UnitOfBat.NORMAL

    # Unknown numeric values map to UNKNOWN
    assert battery_level(2) == UnitOfBat.UNKNOWN
    assert battery_level("2") == UnitOfBat.UNKNOWN


def test_battery_level_to_icon_maps_all_and_unknown():
    assert battery_level_to_icon(UnitOfBat.LOW) == "mdi:battery-low"
    assert battery_level_to_icon(UnitOfBat.NORMAL) == "mdi:battery"
    assert battery_level_to_icon(UnitOfBat.UNKNOWN) == "mdi:battery-unknown"


def test_temperature_conversions_round_trip():
    # Use a value that is exactly representable in binary-ish floats
    f = 32.0
    c = fahrenheit_to_celsius(f)
    assert c == 0.0
    assert celsius_to_fahrenheit(c) == 32.0

    # General check (approx)
    f2 = 77.0
    c2 = fahrenheit_to_celsius(f2)
    assert c2 == pytest.approx(25.0)
    assert celsius_to_fahrenheit(c2) == pytest.approx(77.0)


def test_wind_dir_to_text_returns_none_for_zero_and_valid_for_positive():
    assert wind_dir_to_text(0.0) is None
    assert wind_dir_to_text(0) is None

    # For a non-zero degree it should return some enum value
    out = wind_dir_to_text(10.0)
    assert out is not None


def test_heat_index_returns_none_when_missing_temp_or_humidity(monkeypatch):
    monkeypatch.setattr(
        "custom_components.sws12500.utils._LOGGER.error", lambda *a, **k: None
    )

    assert heat_index({OUTSIDE_HUMIDITY: "50"}) is None
    assert heat_index({OUTSIDE_TEMP: "80"}) is None

    assert heat_index({OUTSIDE_TEMP: "x", OUTSIDE_HUMIDITY: "50"}) is None
    assert heat_index({OUTSIDE_TEMP: "80", OUTSIDE_HUMIDITY: "x"}) is None


def test_heat_index_simple_path_and_full_index_path():
    # Simple path: keep simple average under threshold.
    # Using temp=70F, rh=40 keeps ((simple+temp)/2) under 80 typically.
    simple = heat_index({OUTSIDE_TEMP: "70", OUTSIDE_HUMIDITY: "40"})
    assert simple is not None

    # Full index path: choose high temp/rh -> triggers full index.
    full = heat_index({OUTSIDE_TEMP: "90", OUTSIDE_HUMIDITY: "85"})
    assert full is not None


def test_heat_index_low_humidity_adjustment_branch():
    # This targets:
    # if rh < 13 and (80 <= temp <= 112): adjustment = ...
    #
    # Pick a temp/rh combo that:
    # - triggers the full-index path: ((simple + temp) / 2) > 80
    # - satisfies low humidity adjustment bounds
    out = heat_index({OUTSIDE_TEMP: "95", OUTSIDE_HUMIDITY: "10"})
    assert out is not None


def test_heat_index_convert_from_celsius_path():
    # If convert=True, temp is interpreted as Celsius and converted to Fahrenheit internally.
    # Use 30C (~86F) and high humidity to trigger full index path.
    out = heat_index({OUTSIDE_TEMP: "30", OUTSIDE_HUMIDITY: "85"}, convert=True)
    assert out is not None


def test_chill_index_returns_none_when_missing_temp_or_wind(monkeypatch):
    monkeypatch.setattr(
        "custom_components.sws12500.utils._LOGGER.error", lambda *a, **k: None
    )

    assert chill_index({WIND_SPEED: "10"}) is None
    assert chill_index({OUTSIDE_TEMP: "10"}) is None
    assert chill_index({OUTSIDE_TEMP: "x", WIND_SPEED: "10"}) is None
    assert chill_index({OUTSIDE_TEMP: "10", WIND_SPEED: "x"}) is None


def test_chill_index_returns_calculated_when_cold_and_windy():
    # temp in F, wind > 3 -> calculate when temp < 50
    out = chill_index({OUTSIDE_TEMP: "40", WIND_SPEED: "10"})
    assert out is not None
    assert isinstance(out, float)


def test_chill_index_returns_temp_when_not_cold_or_not_windy():
    # Not cold -> hits the `else temp` branch
    out1 = chill_index({OUTSIDE_TEMP: "60", WIND_SPEED: "10"})
    assert out1 == 60.0

    # Not windy -> hits the `else temp` branch
    out2 = chill_index({OUTSIDE_TEMP: "40", WIND_SPEED: "2"})
    assert out2 == 40.0

    # Boundary: exactly 50F should also hit the `else temp` branch (since condition is temp < 50)
    out3 = chill_index({OUTSIDE_TEMP: "50", WIND_SPEED: "10"})
    assert out3 == 50.0

    # Boundary: exactly 3 mph should also hit the `else temp` branch (since condition is wind > 3)
    out4 = chill_index({OUTSIDE_TEMP: "40", WIND_SPEED: "3"})
    assert out4 == 40.0


def test_chill_index_convert_from_celsius_path():
    out = chill_index({OUTSIDE_TEMP: "5", WIND_SPEED: "10"}, convert=True)
    assert out is not None
