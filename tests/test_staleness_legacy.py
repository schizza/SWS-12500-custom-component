"""Tests for stale-sensor and legacy-battery Repairs issues.

Covers:
- staleness.py: warmup short-circuit, stale detection (never seen / seen long ago),
  fresh sensors clearing the issue, and the create/delete branches of
  `update_stale_sensors_issue`.
- legacy.py: orphan legacy battery sensor detection and the create/delete branches
  of `update_legacy_battery_issue`.

Uses the real `hass` fixture so the issue/entity registries behave like production.
"""

from __future__ import annotations

from datetime import timedelta

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sws12500.const import DOMAIN, SENSORS_TO_LOAD
from custom_components.sws12500.data import SWSRuntimeData
from custom_components.sws12500.legacy import _legacy_battery_issue_id, update_legacy_battery_issue
from custom_components.sws12500.staleness import _find_stale_keys, _stale_sensor_issue_id, update_stale_sensors_issue
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.util import dt as dt_util


def _make_entry(hass, options: dict) -> MockConfigEntry:
    """Create a config entry with typed runtime data attached and added to hass."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options)
    entry.add_to_hass(hass)
    entry.runtime_data = SWSRuntimeData(
        coordinator=object(),  # type: ignore[arg-type]
        health_coordinator=object(),  # type: ignore[arg-type]
        last_options=dict(options),
    )
    return entry


# --------------------------------------------------------------------------- #
# staleness.py
# --------------------------------------------------------------------------- #


async def test_warmup_returns_no_stale_keys_and_no_issue(hass):
    """During the warmup period no key is considered stale and no issue is raised."""
    entry = _make_entry(hass, {SENSORS_TO_LOAD: ["outside_temp"]})
    # started_at = now -> within WARMUP_PERIOD even with a never-seen key.
    entry.runtime_data.started_at = dt_util.utcnow()

    assert _find_stale_keys(entry) == []

    update_stale_sensors_issue(hass, entry)

    issue_id = _stale_sensor_issue_id(entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_never_seen_key_is_stale_and_creates_issue(hass):
    """Past warmup, a loaded key that was never seen is stale -> issue created."""
    entry = _make_entry(hass, {SENSORS_TO_LOAD: ["outside_temp"]})
    entry.runtime_data.started_at = dt_util.utcnow() - timedelta(hours=2)
    # last_seen left empty -> outside_temp never reported.

    assert _find_stale_keys(entry) == ["outside_temp"]

    update_stale_sensors_issue(hass, entry)

    issue_id = _stale_sensor_issue_id(entry)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "stale_sensors_detected"
    assert issue.translation_placeholders == {"sensors": "outside_temp"}


async def test_recently_seen_key_is_not_stale_and_clears_issue(hass):
    """Past warmup, a key seen just now is fresh -> issue absent/cleared."""
    entry = _make_entry(hass, {SENSORS_TO_LOAD: ["outside_temp"]})
    entry.runtime_data.started_at = dt_util.utcnow() - timedelta(hours=2)
    entry.runtime_data.last_seen = {"outside_temp": dt_util.utcnow()}

    assert _find_stale_keys(entry) == []

    update_stale_sensors_issue(hass, entry)

    issue_id = _stale_sensor_issue_id(entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_key_seen_long_ago_is_stale(hass):
    """A key last seen beyond STALE_THRESHOLD (24h) is stale."""
    entry = _make_entry(hass, {SENSORS_TO_LOAD: ["outside_temp"]})
    entry.runtime_data.started_at = dt_util.utcnow() - timedelta(hours=2)
    entry.runtime_data.last_seen = {"outside_temp": dt_util.utcnow() - timedelta(hours=48)}

    assert _find_stale_keys(entry) == ["outside_temp"]


async def test_existing_stale_issue_is_deleted_when_keys_become_fresh(hass):
    """A previously-created stale issue is cleared once the sensor reports again."""
    entry = _make_entry(hass, {SENSORS_TO_LOAD: ["outside_temp"]})
    entry.runtime_data.started_at = dt_util.utcnow() - timedelta(hours=2)

    # First pass: stale -> issue created.
    update_stale_sensors_issue(hass, entry)
    issue_id = _stale_sensor_issue_id(entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    # Sensor reports -> second pass clears the issue.
    entry.runtime_data.last_seen = {"outside_temp": dt_util.utcnow()}
    update_stale_sensors_issue(hass, entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


# --------------------------------------------------------------------------- #
# legacy.py
# --------------------------------------------------------------------------- #


async def test_legacy_battery_sensor_creates_issue(hass):
    """A legacy (non-binary) battery sensor in the entity registry raises an issue."""
    entry = _make_entry(hass, {})

    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create("sensor", DOMAIN, "outside_battery", config_entry=entry)

    update_legacy_battery_issue(hass, entry)

    issue_id = _legacy_battery_issue_id(entry)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "legacy_battery_sensor_deprecated"
    assert issue.translation_placeholders is not None
    assert issue.translation_placeholders["remove_version"] == "2.1.0"


async def test_no_legacy_battery_sensor_clears_issue(hass):
    """With no legacy battery sensor present, the issue is deleted/absent."""
    entry = _make_entry(hass, {})

    update_legacy_battery_issue(hass, entry)

    issue_id = _legacy_battery_issue_id(entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
