"""Tests for the user-facing strings shipped with the integration.

`strings.json` is the source of truth; `translations/en.json` and `translations/cs.json`
are what the frontend actually loads. A key that exists in one file and not in another
(or a state key that no entity ever emits) is invisible in code review and only shows up
as an untranslated raw value in the UI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.sws12500.sensors_weather import SENSOR_TYPES_WEATHER_API
from custom_components.sws12500.sensors_wslink import SENSOR_TYPES_WSLINK
from homeassistant.components.sensor import SensorDeviceClass

COMPONENT_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "sws12500"

STRINGS_FILE = COMPONENT_DIR / "strings.json"
TRANSLATION_FILES = (
    COMPONENT_DIR / "translations" / "en.json",
    COMPONENT_DIR / "translations" / "cs.json",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten(data: dict[str, Any], prefix: str = "") -> set[str]:
    """Return every leaf path in a translation document."""
    keys: set[str] = set()
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys |= _flatten(value, path)
        else:
            keys.add(path)
    return keys


@pytest.mark.parametrize("translation_file", TRANSLATION_FILES, ids=lambda p: p.name)
def test_translation_keys_match_strings_json(translation_file: Path) -> None:
    """Every shipped language must carry exactly the keys defined in strings.json."""
    expected = _flatten(_load(STRINGS_FILE))
    actual = _flatten(_load(translation_file))

    assert not expected - actual, f"{translation_file.name} is missing keys"
    assert not actual - expected, f"{translation_file.name} has stale keys"


def _enum_descriptions() -> list[Any]:
    """Sensor descriptions that report a fixed set of states to the frontend."""
    seen: dict[str, Any] = {}
    for description in (*SENSOR_TYPES_WEATHER_API, *SENSOR_TYPES_WSLINK):
        if description.device_class is not SensorDeviceClass.ENUM or not description.options:
            continue
        seen.setdefault(description.translation_key or description.key, description)
    return list(seen.values())


@pytest.mark.parametrize(
    ("path", "description"),
    [(path, description) for path in (STRINGS_FILE, *TRANSLATION_FILES) for description in _enum_descriptions()],
    ids=lambda value: value.name if isinstance(value, Path) else (value.translation_key or value.key),
)
def test_enum_states_are_translated(path: Path, description: Any) -> None:
    """Each enum state an entity can emit needs a translation - and no extra ones.

    The battery sensors emit `UnitOfBat.UNKNOWN`, whose *value* is "drained"; a state
    block keyed on the member name ("unknown") never matches, so the frontend falls back
    to showing the raw state.
    """
    translation_key = description.translation_key or description.key
    states = _load(path)["entity"]["sensor"][translation_key]["state"]

    assert set(states) == {str(option) for option in description.options}, (
        f"{path.name}: state keys for '{translation_key}' do not match the emitted values"
    )
