"""End-to-end proof that the rename does not cost a single measurement.

`test_predecessor_adoption.py` proves the registry side of the move: the `entity_id`
does not change. This file closes the loop the user actually cares about by putting a
real recorder behind it - short-term history *and* long-term statistics are written for
the predecessor's entity, the new integration is then set up exactly as a user would set
it up (config flow options, real HTTP upload from the station), and the same rows are
read back afterwards through the same API the History and Statistics panels use.

The scenario mirrors the documented upgrade procedure:

1. The old integration ran and recorded measurements.
2. Its repository was swapped in HACS, so its files are gone and its entities sit at
   `unavailable` with `restored: true` while its config entry stays behind.
3. The user adds the renamed integration, typing only the credentials.

Set ``SWS_MIGRATION_REPORT`` to a file path to dump the before/after transcript.
"""

from __future__ import annotations

from datetime import timedelta
import os
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

from custom_components.sws12500.const import (
    API_ID,
    API_KEY,
    DOMAIN,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    SENSORS_TO_LOAD,
    WSLINK,
    WSLINK_URL,
)
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics, statistics_during_period
from homeassistant.components.recorder.util import get_instance
from homeassistant.const import ATTR_RESTORED, STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

OLD_DOMAIN = "sws12500_legacy"

STATION_ID = "migration-station"
STATION_PW = "migration-secret"

# The object id the old integration handed out. Deliberately unlike anything the current
# naming scheme produces, so a recreated entity is impossible to confuse with a moved one.
OLD_OBJECT_ID = "sws12500_outside_temp"
OLD_ENTITY_ID = f"sensor.{OLD_OBJECT_ID}"

# Three readings recorded by the old integration, before anything was renamed.
HISTORIC_READINGS = ("18.6", "19.4", "20.2")

# What the station uploads once the renamed integration is running.
NEW_READING = "21.7"

ATTRS: dict[str, Any] = {
    "unit_of_measurement": UnitOfTemperature.CELSIUS,
    "device_class": "temperature",
    "state_class": "measurement",
    "friendly_name": "Outside temperature",
}


@pytest.fixture(autouse=True)
def _recorder(recorder_mock) -> None:
    """Every test here needs a real recorder behind the registries."""


def _upload(**overrides: str) -> dict[str, str]:
    """A minimal WSLink upload carrying the outside temperature and humidity."""
    return {
        "wsid": STATION_ID,
        "wspw": STATION_PW,
        "apiver": "0.6",
        "t1tem": NEW_READING,
        "t1hum": "62",
        **overrides,
    }


async def _record_predecessor_history(hass: HomeAssistant) -> MockConfigEntry:
    """Run the old integration's lifetime: entities, measurements, then uninstalled."""
    old = MockConfigEntry(
        domain=OLD_DOMAIN,
        title="Sencor SWS 12500",
        options={
            API_ID: STATION_ID,
            API_KEY: STATION_PW,
            WSLINK: True,
            SENSORS_TO_LOAD: [OUTSIDE_TEMP, OUTSIDE_HUMIDITY],
        },
    )
    old.add_to_hass(hass)

    registry = er.async_get(hass)
    registered = registry.async_get_or_create(
        "sensor",
        OLD_DOMAIN,
        OUTSIDE_TEMP,
        config_entry=old,
        suggested_object_id=OLD_OBJECT_ID,
        original_name="Outside temperature",
    )
    assert registered.entity_id == OLD_ENTITY_ID

    for reading in HISTORIC_READINGS:
        hass.states.async_set(OLD_ENTITY_ID, reading, ATTRS)
        await hass.async_block_till_done()
    await async_wait_recording_done(hass)

    # Long-term statistics, the rows behind the "Statistics" graph. Keyed on the same
    # entity_id, which is the whole point of the exercise.
    start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    async_import_statistics(
        hass,
        {
            "mean_type": StatisticMeanType.ARITHMETIC,
            "has_sum": False,
            "name": None,
            "source": "recorder",
            "statistic_id": OLD_ENTITY_ID,
            "unit_class": "temperature",
            "unit_of_measurement": UnitOfTemperature.CELSIUS,
        },
        [
            {"start": start, "mean": 18.6, "min": 18.0, "max": 19.0},
            {"start": start + timedelta(hours=1), "mean": 19.8, "min": 19.4, "max": 20.2},
        ],
    )
    await async_wait_recording_done(hass)

    # HACS swap done, files gone: this is the placeholder state Home Assistant writes for
    # a registered entity nothing is driving any more.
    hass.states.async_set(OLD_ENTITY_ID, STATE_UNAVAILABLE, {**ATTRS, ATTR_RESTORED: True})
    await hass.async_block_till_done()

    return old


async def _history_for(hass: HomeAssistant, entity_id: str, since) -> list[str]:
    """Read back the recorded states the History panel would draw."""
    states = await get_instance(hass).async_add_executor_job(
        get_significant_states, hass, since, None, [entity_id]
    )
    return [state.state for state in states.get(entity_id, [])]


async def _statistics_for(hass: HomeAssistant, entity_id: str, since) -> list[float]:
    """Read back the long-term statistics the Statistics panel would draw."""
    rows = await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, since, None, {entity_id}, "hour", None, {"mean"}
    )
    return [row["mean"] for row in rows.get(entity_id, [])]


@pytest.fixture
async def migrated(
    hass: HomeAssistant,
    enable_custom_integrations,
    hass_client_no_auth,
    monkeypatch: pytest.MonkeyPatch,
):
    """The full move: recorded predecessor, renamed integration set up over the top."""
    assert await async_setup_component(hass, "http", {"http": {}})
    since = dt_util.utcnow() - timedelta(hours=3)

    old = await _record_predecessor_history(hass)
    before = await _history_for(hass, OLD_ENTITY_ID, since)
    statistics_before = await _statistics_for(hass, OLD_ENTITY_ID, since)

    # The rename itself. In the new repository this is a source change; here it is the
    # one thing that has to be simulated, because both domains are still `sws12500`.
    monkeypatch.setattr("custom_components.sws12500.predecessor.PREDECESSOR_DOMAIN", OLD_DOMAIN)

    # What the user types into the new integration's config flow: the credentials, and
    # nothing else. The protocol flag and the sensor list are inherited.
    new = MockConfigEntry(
        domain=DOMAIN,
        title="Sencor SWS 12500",
        options={API_ID: STATION_ID, API_KEY: STATION_PW},
    )
    new.add_to_hass(hass)
    assert await hass.config_entries.async_setup(new.entry_id)
    await hass.async_block_till_done()

    # The station uploads again, to the endpoint the inherited WSLINK flag opened.
    client = await hass_client_no_auth()
    response = await client.get(WSLINK_URL, params=_upload())
    assert response.status == 200
    assert await response.text() == "OK"
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)

    return {
        "old_entry": old,
        "new_entry": new,
        "since": since,
        "history_before": before,
        "history_after": await _history_for(hass, OLD_ENTITY_ID, since),
        "statistics_before": statistics_before,
        "statistics_after": await _statistics_for(hass, OLD_ENTITY_ID, since),
    }


async def test_the_measurements_survive_the_move(hass: HomeAssistant, migrated) -> None:
    """One series, one entity_id, spanning both integrations."""
    assert migrated["history_before"] == [*HISTORIC_READINGS, STATE_UNAVAILABLE]

    # Everything recorded before the move is still there, and the reading the renamed
    # integration just took continues the same series.
    after = migrated["history_after"]
    assert after[: len(HISTORIC_READINGS)] == list(HISTORIC_READINGS)
    assert after[-1] == NEW_READING

    # Long-term statistics hang off the same entity_id and are untouched.
    assert migrated["statistics_after"] == migrated["statistics_before"] == [18.6, 19.8]


async def test_the_entity_is_the_same_row_now_owned_by_the_new_integration(
    hass: HomeAssistant, migrated, entity_registry: er.EntityRegistry
) -> None:
    """Moved, not recreated: same entity_id, new platform, no duplicate left behind."""
    moved = entity_registry.async_get(OLD_ENTITY_ID)
    assert moved is not None
    assert moved.platform == DOMAIN
    assert moved.config_entry_id == migrated["new_entry"].entry_id

    # Nothing was created under the current naming scheme for the same reading, which is
    # what an unmigrated install would have produced.
    duplicates = [
        entry.entity_id
        for entry in er.async_entries_for_config_entry(entity_registry, migrated["new_entry"].entry_id)
        if entry.unique_id == OUTSIDE_TEMP and entry.entity_id != OLD_ENTITY_ID
    ]
    assert duplicates == []

    # The live state is the new upload, on the old entity_id.
    state = hass.states.get(OLD_ENTITY_ID)
    assert state is not None
    assert state.state == NEW_READING

    # The predecessor's config entry is gone, so Settings is clean.
    assert hass.config_entries.async_entries(OLD_DOMAIN) == []


async def test_options_the_user_never_retyped_came_across(hass: HomeAssistant, migrated) -> None:
    """The upload above only worked because WSLINK was inherited before the routes."""
    options = migrated["new_entry"].options
    assert options[WSLINK] is True
    assert OUTSIDE_TEMP in options[SENSORS_TO_LOAD]
    # And the credentials the user did retype are the ones in force.
    assert options[API_ID] == STATION_ID


async def test_without_the_move_the_history_is_orphaned(
    hass: HomeAssistant,
    enable_custom_integrations,
    hass_client_no_auth,
    entity_registry: er.EntityRegistry,
) -> None:
    """The counterfactual, and the shipped default: `PREDECESSOR_DOMAIN == DOMAIN`.

    Nothing is adopted, so the new integration mints its own entity under the current
    naming scheme and the recorded series stops at `unavailable`. This is what the
    migration exists to prevent - and, until the domain actually changes, also proof that
    the adoption pass is inert rather than quietly rewriting a live installation.
    """
    assert await async_setup_component(hass, "http", {"http": {}})
    since = dt_util.utcnow() - timedelta(hours=3)

    old = await _record_predecessor_history(hass)

    new = MockConfigEntry(
        domain=DOMAIN,
        title="Sencor SWS 12500",
        options={API_ID: STATION_ID, API_KEY: STATION_PW, WSLINK: True},
    )
    new.add_to_hass(hass)
    assert await hass.config_entries.async_setup(new.entry_id)
    await hass.async_block_till_done()

    client = await hass_client_no_auth()
    assert (await client.get(WSLINK_URL, params=_upload())).status == 200
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)

    # A second entity id for the same reading; the old series ends where it ended.
    fresh = entity_registry.async_get_entity_id("sensor", DOMAIN, OUTSIDE_TEMP)
    assert fresh is not None
    assert fresh != OLD_ENTITY_ID
    assert await _history_for(hass, OLD_ENTITY_ID, since) == [*HISTORIC_READINGS, STATE_UNAVAILABLE]
    # The new entity starts from `unknown`, as any freshly created one does, and knows
    # nothing of what came before.
    assert await _history_for(hass, fresh, since) == [STATE_UNKNOWN, NEW_READING]

    # The predecessor's entry is untouched, exactly as before this change.
    assert hass.config_entries.async_entries(OLD_DOMAIN) == [old]


async def test_write_migration_report(hass: HomeAssistant, migrated, entity_registry: er.EntityRegistry) -> None:
    """Dump the before/after transcript when SWS_MIGRATION_REPORT names a file."""
    target = os.environ.get("SWS_MIGRATION_REPORT")
    if not target:
        pytest.skip("SWS_MIGRATION_REPORT not set")

    moved = entity_registry.async_get(OLD_ENTITY_ID)
    assert moved is not None
    lines = [
        f"Domain move: {OLD_DOMAIN} -> {DOMAIN}",
        "",
        "BEFORE (old integration recorded, then uninstalled)",
        f"  entity_id            : {OLD_ENTITY_ID}",
        f"  platform             : {OLD_DOMAIN}",
        f"  recorded states      : {', '.join(migrated['history_before'])}",
        f"  long-term statistics : {migrated['statistics_before']}",
        "",
        f"AFTER (renamed integration set up, station uploaded {NEW_READING} C)",
        f"  entity_id            : {moved.entity_id}",
        f"  platform             : {moved.platform}",
        f"  config entry         : {moved.config_entry_id} ({migrated['new_entry'].domain})",
        f"  recorded states      : {', '.join(migrated['history_after'])}",
        f"  long-term statistics : {migrated['statistics_after']}",
        f"  live state           : {hass.states.get(OLD_ENTITY_ID).state} C",
        f"  inherited options    : {WSLINK}={migrated['new_entry'].options[WSLINK]}, "
        f"{SENSORS_TO_LOAD}={migrated['new_entry'].options[SENSORS_TO_LOAD]}",
        f"  predecessor entries  : {hass.config_entries.async_entries(OLD_DOMAIN)}",
        "",
        "entity_id unchanged, history and statistics continue in one series.",
    ]
    Path(target).write_text("\n".join(lines) + "\n", encoding="utf-8")
