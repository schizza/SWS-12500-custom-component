"""Adopting the predecessor integration must not cost a single measurement.

Recorder history and long-term statistics hang off `entity_id`. Every test here exists
to defend one sentence: after adoption the `entity_id` is byte-for-byte what it was.
Everything else - the platform, the config entry, the device - may change freely.

The tests drive the real entity and device registries rather than stubs, because the
failure modes being guarded against (a placeholder `unavailable` state blocking the
migration, a device deleted with its entities in tow, a duplicate unique id landing in
the registry index) all live inside Home Assistant's own bookkeeping.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sws12500.const import (
    CHANNEL_TYPES,
    DOMAIN,
    POCASI_CZ_ENABLED,
    POCASI_CZ_ENABLED_LEGACY,
    SENSORS_TO_LOAD,
)
from custom_components.sws12500.data import build_device_info
from custom_components.sws12500.predecessor import async_adopt_predecessor
from homeassistant.const import ATTR_RESTORED, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

OLD_DOMAIN = "sws12500_legacy"

# A representative slice: a plain sensor, a binary sensor, and the suffixed unique id
# the battery entities use.
SEEDED = (
    ("sensor", "outside_temp"),
    ("sensor", "lightning_distance"),
    ("binary_sensor", "leak_ch1_binary"),
)


@pytest.fixture
def entries(hass: HomeAssistant) -> tuple[MockConfigEntry, MockConfigEntry]:
    """A predecessor entry with entities, plus the new entry adopting them."""
    old = MockConfigEntry(domain=OLD_DOMAIN, title="Old", options={"api_id": "x"})
    old.add_to_hass(hass)
    new = MockConfigEntry(domain=DOMAIN, title="New")
    new.add_to_hass(hass)
    return old, new


def _seed(hass: HomeAssistant, old: MockConfigEntry, **kwargs: Any) -> dict[str, str]:
    """Register the predecessor's entities; returns unique_id -> entity_id."""
    registry = er.async_get(hass)
    created: dict[str, str] = {}
    for domain, unique_id in SEEDED:
        entry = registry.async_get_or_create(
            domain, OLD_DOMAIN, unique_id, config_entry=old, **kwargs
        )
        created[unique_id] = entry.entity_id
    return created


# ---------------------------------------------------------------------------
# The one that matters
# ---------------------------------------------------------------------------


async def test_entity_ids_are_untouched(hass: HomeAssistant, entries) -> None:
    """History follows entity_id. If this test fails, users lose their measurements."""
    old, new = entries
    before = _seed(hass, old)

    result = await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    registry = er.async_get(hass)
    for unique_id, entity_id in before.items():
        adopted = registry.async_get_entity_id(entity_id.split(".")[0], DOMAIN, unique_id)
        assert adopted == entity_id, f"{unique_id} changed entity_id: {entity_id} -> {adopted}"

    assert sorted(result.adopted) == sorted(before.values())
    assert result.complete


async def test_unique_ids_are_untouched(hass: HomeAssistant, entries) -> None:
    """A rewritten unique id would break the bind between platform and registry entry."""
    old, new = entries
    _seed(hass, old)

    await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    registry = er.async_get(hass)
    adopted = {e.unique_id for e in er.async_entries_for_config_entry(registry, new.entry_id)}
    assert adopted == {unique_id for _, unique_id in SEEDED}


async def test_platform_and_config_entry_are_repointed(hass: HomeAssistant, entries) -> None:
    """The registry entry has to end up owned by this integration."""
    old, new = entries
    _seed(hass, old)

    await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    registry = er.async_get(hass)
    assert not er.async_entries_for_config_entry(registry, old.entry_id)
    for entry in er.async_entries_for_config_entry(registry, new.entry_id):
        assert entry.platform == DOMAIN


async def test_user_customisations_survive(hass: HomeAssistant, entries) -> None:
    """Renames, icons and placement are part of what the user would lose on a recreate."""
    old, new = entries
    created = _seed(hass, old)
    registry = er.async_get(hass)
    entity_id = created["outside_temp"]
    registry.async_update_entity(
        entity_id,
        name="Teplota na zahradě",
        icon="mdi:thermometer",
        area_id="garden",
    )

    await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    entry = registry.async_get(entity_id)
    assert entry is not None
    assert entry.name == "Teplota na zahradě"
    assert entry.icon == "mdi:thermometer"
    assert entry.area_id == "garden"


# ---------------------------------------------------------------------------
# The trap: the placeholder state Home Assistant writes for unloaded entities
# ---------------------------------------------------------------------------


async def test_restored_placeholder_does_not_block_adoption(hass: HomeAssistant, entries) -> None:
    """The exact production state: old files gone, entities restored as `unavailable`.

    `async_update_entity_platform` accepts only a missing state or `unknown`, and on
    startup HA writes `unavailable` + ATTR_RESTORED for every registered but unloaded
    entity. Without clearing that placeholder first, every adoption raises ValueError -
    which is to say, nobody's history would migrate at all.
    """
    old, new = entries
    created = _seed(hass, old)
    for entity_id in created.values():
        hass.states.async_set(entity_id, STATE_UNAVAILABLE, {ATTR_RESTORED: True})

    result = await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert result.complete
    assert sorted(result.adopted) == sorted(created.values())


async def test_unknown_state_is_accepted(hass: HomeAssistant, entries) -> None:
    """`unknown` is what the registry API itself tolerates."""
    old, new = entries
    created = _seed(hass, old)
    hass.states.async_set(created["outside_temp"], STATE_UNKNOWN)

    result = await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert result.complete


async def test_live_entity_is_refused(hass: HomeAssistant, entries) -> None:
    """A real state means someone owns this entity; stealing it would give it two owners."""
    old, new = entries
    created = _seed(hass, old)
    live = created["outside_temp"]
    hass.states.async_set(live, "21.5")  # no ATTR_RESTORED: a genuine reading

    result = await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert result.live == [live]
    assert not result.complete
    registry = er.async_get(hass)
    still_old = registry.async_get(live)
    assert still_old is not None
    assert still_old.platform == OLD_DOMAIN, "a live entity must be left exactly as it was"


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------


async def test_unique_id_conflict_is_refused(hass: HomeAssistant, entries) -> None:
    """HA does not guard this itself when only the platform changes.

    `_async_update_entity` checks for a duplicate unique id only when `new_unique_id` is
    passed. Changing just the platform onto a key this integration already uses would
    put two registry entries on one index slot, and the loser becomes unreachable.
    """
    old, new = entries
    created = _seed(hass, old)
    registry = er.async_get(hass)
    ours = registry.async_get_or_create("sensor", DOMAIN, "outside_temp", config_entry=new)

    result = await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert result.conflicting == [created["outside_temp"]]
    # Both entries still exist and still resolve to different entity_ids.
    assert registry.async_get_entity_id("sensor", DOMAIN, "outside_temp") == ours.entity_id
    assert registry.async_get_entity_id("sensor", OLD_DOMAIN, "outside_temp") == created["outside_temp"]


async def test_predecessor_is_kept_when_anything_was_skipped(hass: HomeAssistant, entries) -> None:
    """Removing the old entry deletes whatever is still attached to it."""
    old, new = entries
    created = _seed(hass, old)
    hass.states.async_set(created["outside_temp"], "21.5")

    result = await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert not result.predecessor_removed
    assert hass.config_entries.async_get_entry(old.entry_id) is not None
    registry = er.async_get(hass)
    assert registry.async_get(created["outside_temp"]) is not None


async def test_predecessor_is_removed_when_complete(hass: HomeAssistant, entries) -> None:
    """A finished migration must not leave a broken entry behind in the UI."""
    old, new = entries
    _seed(hass, old)

    result = await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert result.predecessor_removed
    assert hass.config_entries.async_get_entry(old.entry_id) is None


# ---------------------------------------------------------------------------
# Devices - the second way to lose entities
# ---------------------------------------------------------------------------


async def test_device_is_repointed_and_keeps_its_entities(hass: HomeAssistant, entries) -> None:
    """Deleting a device deletes its entities, so the device has to move, not be replaced."""
    old, new = entries
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=old.entry_id,
        identifiers={(OLD_DOMAIN,)},  # type: ignore[arg-type]
        name="Weather Station",
    )
    created = _seed(hass, old, device_id=device.id)

    await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    survived = device_registry.async_get(device.id)
    assert survived is not None, "the device was deleted, which takes its entities with it"
    assert survived.identifiers == set(build_device_info(new)["identifiers"])
    assert new.entry_id in survived.config_entries
    assert old.entry_id not in survived.config_entries

    registry = er.async_get(hass)
    for entity_id in created.values():
        entry = registry.async_get(entity_id)
        assert entry is not None
        assert entry.device_id == device.id


async def test_device_identifiers_match_what_the_platform_will_look_up(
    hass: HomeAssistant, entries
) -> None:
    """If adoption and `build_device_info` drift, setup mints a second device.

    The adopted device would then be stranded and every entity would be moved onto the
    new one. History survives that, but the device page does not.
    """
    old, new = entries
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=old.entry_id,
        identifiers={(OLD_DOMAIN,)},  # type: ignore[arg-type]
        name="Weather Station",
    )
    _seed(hass, old, device_id=device.id)

    await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    looked_up = device_registry.async_get_device(identifiers=set(build_device_info(new)["identifiers"]))
    assert looked_up is not None
    assert looked_up.id == device.id


# ---------------------------------------------------------------------------
# Repeatability
# ---------------------------------------------------------------------------


async def test_running_twice_changes_nothing(hass: HomeAssistant, entries) -> None:
    """Adoption runs on every setup, so the second pass must be inert."""
    old, new = entries
    before = _seed(hass, old)

    await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)
    second = await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert not second.attempted
    registry = er.async_get(hass)
    for unique_id, entity_id in before.items():
        assert registry.async_get_entity_id(entity_id.split(".")[0], DOMAIN, unique_id) == entity_id


async def test_a_partial_run_can_be_finished(hass: HomeAssistant, entries) -> None:
    """Interrupted migration: the retry has to pick up what was left behind."""
    old, new = entries
    created = _seed(hass, old)
    blocked = created["outside_temp"]
    hass.states.async_set(blocked, "21.5")

    first = await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)
    assert first.live == [blocked]

    # The blocker goes away (old integration finally unloaded / HA restarted).
    hass.states.async_remove(blocked)
    second = await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert second.adopted == [blocked]
    assert second.complete
    assert second.predecessor_removed
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", DOMAIN, "outside_temp") == blocked


async def test_no_predecessor_is_a_noop(hass: HomeAssistant) -> None:
    """The overwhelmingly common case: a fresh install, on every single restart."""
    new = MockConfigEntry(domain=DOMAIN)
    new.add_to_hass(hass)

    result = await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert not result.attempted
    assert not result.predecessor_removed


# ---------------------------------------------------------------------------
# Settings - without them the adopted entities have nothing asking for them
# ---------------------------------------------------------------------------


async def test_settings_are_inherited(hass: HomeAssistant, entries) -> None:
    """`SENSORS_TO_LOAD` is what makes the platform create an entity at all.

    Adopting the registry but not this leaves every entity showing "no longer provided"
    until auto-discovery has seen a payload - and derived sensors, which are never in a
    payload, only reappear on the next restart. The forwarding credentials would have
    to be typed in again on top of that.
    """
    old, new = entries
    hass.config_entries.async_update_entry(
        old,
        options={
            SENSORS_TO_LOAD: ["outside_temp", "wind_dir"],
            "WINDY_API_KEY": "windy-secret",
            CHANNEL_TYPES: {"t234c1tp": "4"},
        },
    )

    await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert new.options[SENSORS_TO_LOAD] == ["outside_temp", "wind_dir"]
    assert new.options["WINDY_API_KEY"] == "windy-secret"
    assert new.options[CHANNEL_TYPES] == {"t234c1tp": "4"}


async def test_fresh_input_wins_over_inherited(hass: HomeAssistant, entries) -> None:
    """What the user just typed into this integration's flow is newer by definition."""
    old, new = entries
    hass.config_entries.async_update_entry(old, options={"API_ID": "old-id", "API_KEY": "old-key"})
    hass.config_entries.async_update_entry(new, options={"API_ID": "new-id"})

    await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert new.options["API_ID"] == "new-id", "the freshly entered value must not be overwritten"
    assert new.options["API_KEY"] == "old-key", "gaps are still filled from the predecessor"


async def test_the_misspelled_pocasi_flag_is_translated(hass: HomeAssistant, entries) -> None:
    """A version 1 entry carries the old spelling, and `async_migrate_entry` cannot help.

    Migration runs against this entry's own version, which is already current, so a key
    copied in afterwards would never be looked at again - and Pocasi forwarding would
    silently come up disabled.
    """
    old, new = entries
    hass.config_entries.async_update_entry(old, options={POCASI_CZ_ENABLED_LEGACY: True})

    await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert new.options[POCASI_CZ_ENABLED] is True
    assert POCASI_CZ_ENABLED_LEGACY not in new.options


async def test_a_correct_flag_is_not_clobbered_by_the_misspelled_one(hass: HomeAssistant, entries) -> None:
    """A partially upgraded entry can carry both; the correct spelling has to win."""
    old, new = entries
    hass.config_entries.async_update_entry(
        old, options={POCASI_CZ_ENABLED_LEGACY: True, POCASI_CZ_ENABLED: False}
    )

    await async_adopt_predecessor(hass, new, predecessor_domain=OLD_DOMAIN)

    assert new.options[POCASI_CZ_ENABLED] is False


async def test_a_failed_setup_leaves_the_predecessor_untouched(hass, entries, monkeypatch) -> None:
    """The destructive step must come after setup is known to work.

    Removing the predecessor's config entry is the one thing adoption cannot undo. If
    it ran before the webhook routes were up, a user who still has the previous version
    installed - which is exactly what causes the route clash - would get their old entry
    deleted and then a failed setup, with nothing to fall back to.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from custom_components.sws12500 import async_setup_entry
    from custom_components.sws12500.const import API_ID, API_KEY
    from homeassistant.exceptions import ConfigEntryNotReady

    old, new = entries
    before = _seed(hass, old)
    hass.config_entries.async_update_entry(old, options={API_ID: "id", API_KEY: "key"})

    class _BrokenRouter:
        def add_get(self, *_a: Any, **_kw: Any) -> Any:
            raise ValueError("Duplicate '_default_route', already handled by ...")

        def add_post(self, *_a: Any, **_kw: Any) -> Any:
            raise ValueError("Duplicate '_wslink_post_route', already handled by ...")

    hass.http = SimpleNamespace(app=SimpleNamespace(router=_BrokenRouter()))
    monkeypatch.setattr(
        "custom_components.sws12500.HealthCoordinator.async_config_entry_first_refresh",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("custom_components.sws12500.PREDECESSOR_DOMAIN", OLD_DOMAIN, raising=False)
    monkeypatch.setattr("custom_components.sws12500.predecessor.PREDECESSOR_DOMAIN", OLD_DOMAIN)

    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, new)

    assert hass.config_entries.async_get_entry(old.entry_id) is not None, (
        "the predecessor was removed even though setup failed"
    )
    registry = er.async_get(hass)
    for entity_id in before.values():
        entry = registry.async_get(entity_id)
        assert entry is not None
        assert entry.platform == OLD_DOMAIN

    # Settings are additive and safe to inherit early, so those may already be across.
    assert new.options[API_ID] == "id"


async def test_adoption_runs_before_any_entity_is_created(hass, monkeypatch) -> None:
    """Ordering inside `async_setup_entry`, and it fails silently if broken.

    Adoption has to finish before `async_forward_entry_setups`. Run the other way round,
    our platforms register first, take the free entity_ids for themselves, and the
    predecessor's entries are then left holding ids nobody reads - no error, no warning,
    just every user's history detached.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from custom_components.sws12500 import async_setup_entry
    from custom_components.sws12500.const import API_ID, API_KEY, WSLINK

    class _Router:
        def add_get(self, *_a: Any, **_kw: Any) -> Any:
            return SimpleNamespace(method="GET")

        def add_post(self, *_a: Any, **_kw: Any) -> Any:
            return SimpleNamespace(method="POST")

    hass.http = SimpleNamespace(app=SimpleNamespace(router=_Router()))
    entry = MockConfigEntry(domain=DOMAIN, options={API_ID: "id", API_KEY: "key", WSLINK: False})
    entry.add_to_hass(hass)

    calls: list[str] = []
    monkeypatch.setattr(
        "custom_components.sws12500.HealthCoordinator.async_config_entry_first_refresh",
        AsyncMock(return_value=None),
    )

    async def _adopt(*_a: Any, **_kw: Any) -> Any:
        calls.append("adopt")
        return SimpleNamespace(adopted=[], live=[], conflicting=[], complete=True, attempted=False)

    async def _forward(*_a: Any, **_kw: Any) -> bool:
        calls.append("forward")
        return True

    monkeypatch.setattr("custom_components.sws12500.async_adopt_predecessor", _adopt)
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", _forward)

    assert await async_setup_entry(hass, entry) is True
    assert calls == ["adopt", "forward"], f"adoption must precede entity creation, got {calls}"


async def test_same_domain_short_circuits(hass: HomeAssistant) -> None:
    """Until the rename actually happens, this must never touch anything."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    ours = registry.async_get_or_create("sensor", DOMAIN, "outside_temp", config_entry=entry)

    result = await async_adopt_predecessor(hass, entry, predecessor_domain=DOMAIN)

    assert not result.attempted
    assert registry.async_get(ours.entity_id) is not None
    assert hass.config_entries.async_get_entry(entry.entry_id) is not None
