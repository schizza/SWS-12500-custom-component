"""Adopt the predecessor integration's entities without losing their history.

Home Assistant keys recorder history and long-term statistics on `entity_id`, not on the
integration domain: `recorder/entity_registry.py` renames both `states_meta.entity_id`
and `statistics_meta.statistic_id` when - and only when - an `entity_id` changes. A
domain change therefore costs nothing *provided the registry entries are carried over
rather than recreated*. A recreated entity gets a fresh `entity_id` (or the same one
with an `_2` suffix, if the old entry still holds it) and its history is orphaned.

`entity_registry.async_update_entity_platform` is the supported way to carry them over.
It rewrites `platform` and `config_entry_id` and leaves `entity_id` alone. Everything
the user set by hand rides along for free, because the registry entry itself survives:
renames, icons, areas, labels, categories, hidden and disabled state.

This constrains the upgrade procedure:

1. Do **not** delete the old integration under Settings first. That path calls
   `entity_registry.async_clear_config_entry`, which removes exactly the entries this
   module needs. Once they are gone the history cannot be relinked.
2. Swap the repository in HACS and restart. The old entry stays behind in
   `SETUP_ERROR` ("Integration not found"), which is expected and is the state adoption
   needs.
3. Add this integration. Adoption runs during setup, before any of our own entities are
   created, so the migrated entries are the ones our platforms bind to.

The README carries the general form of the warning - remove the repository in HACS, never
the entry under Settings. The step-by-step procedure needs the new repository's name and
URL, which do not exist yet, so it is written there once they do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_RESTORED, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.helpers.issue_registry import IssueSeverity

from .const import DOMAIN, POCASI_CZ_ENABLED, POCASI_CZ_ENABLED_LEGACY, PREDECESSOR_DOMAIN
from .data import build_device_info

_LOGGER = logging.getLogger(__name__)

# How many stranded entities the repair notice names before it falls back to the count.
ISSUE_ENTITY_SAMPLE: Final = 5


@dataclass(slots=True)
class AdoptionResult:
    """Outcome of one adoption pass, so the caller can report it and retry."""

    adopted: list[str] = field(default_factory=list)
    live: list[str] = field(default_factory=list)
    conflicting: list[str] = field(default_factory=list)
    predecessor_removed: bool = False

    @property
    def complete(self) -> bool:
        """Whether every entity of the predecessor was carried over."""
        return not self.live and not self.conflicting

    @property
    def attempted(self) -> bool:
        """Whether there was anything to do at all."""
        return bool(self.adopted or self.live or self.conflicting)

    @property
    def skipped(self) -> list[str]:
        """Every entity that stayed behind, whatever the reason."""
        return [*self.live, *self.conflicting]

    def absorb(self, other: AdoptionResult) -> None:
        """Fold one predecessor entry's outcome into the running total.

        Completeness has to be decided per predecessor entry, not on the running total.
        There can be more than one - the predecessor's manifest never declared
        `single_config_entry` - and a single blocked entity under the first one would
        otherwise condemn every later entry to be kept forever, even a fully adopted one.
        """

        self.adopted.extend(other.adopted)
        self.live.extend(other.live)
        self.conflicting.extend(other.conflicting)
        self.predecessor_removed |= other.predecessor_removed


def _release_restored_state(hass: HomeAssistant, entity_id: str) -> bool:
    """Drop the placeholder state Home Assistant writes for an unloaded entity.

    At startup `entity_registry._write_unavailable_states` gives every registered but
    unloaded entity a state of `unavailable` carrying `ATTR_RESTORED`. That is exactly
    the state the predecessor's entities are in once its files are gone from disk - and
    `async_update_entity_platform` accepts only a missing state or `unknown`, so without
    clearing the placeholder first every single adoption would raise `ValueError`.

    Returns False when a state is present that is *not* a placeholder. That means some
    integration is still driving this entity, and moving it out from under a live
    platform would leave two owners for one registry entry.
    """

    state = hass.states.get(entity_id)
    if state is None or state.state == STATE_UNKNOWN:
        return True

    if not state.attributes.get(ATTR_RESTORED):
        return False

    hass.states.async_remove(entity_id)
    return True


def inherit_predecessor_options(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    predecessor_domain: str | None = None,
) -> bool:
    """Carry the predecessor's settings over, without overwriting fresh input.

    Deliberately separate from `async_adopt_predecessor`, and deliberately run earlier:
    setup reads the options while wiring up the coordinator and the webhook routes, so
    inheriting an option after that point would leave the entry running on the wrong
    protocol until the next reload. It is also additive and reversible in a way the rest
    of adoption is not, which is why it can safely run before the routes are proven.

    Adopting the registry alone would not be enough anyway. `SENSORS_TO_LOAD` decides
    which entities the platform creates, so an empty one leaves every adopted entry
    showing "no longer provided" until auto-discovery has seen a payload - and derived
    sensors like the wind azimut are never in a payload at all, so those come back only
    on the next restart. The forwarding credentials and the learned probe types would
    likewise have to be entered again.

    Merged the other way round from what reads naturally: the predecessor fills gaps
    only. Anything the user just entered in this integration's config flow is newer by
    definition and wins.

    The version 1 spelling of the Pocasi Meteo flag is translated on the way in, because
    `async_migrate_entry` runs against this entry's own version - already current - and
    would never look at a key copied in afterwards.
    """

    predecessor_domain = predecessor_domain or PREDECESSOR_DOMAIN
    if predecessor_domain == DOMAIN:
        return False

    if not (old_entries := hass.config_entries.async_entries(predecessor_domain)):
        return False

    inherited: dict[str, object] = {}
    for old_entry in old_entries:
        inherited.update(old_entry.options)

    if POCASI_CZ_ENABLED_LEGACY in inherited:
        legacy_value = inherited.pop(POCASI_CZ_ENABLED_LEGACY)
        inherited.setdefault(POCASI_CZ_ENABLED, legacy_value)

    merged = {**inherited, **entry.options}
    if merged == dict(entry.options):
        return False

    gained = len(merged) - len(entry.options)
    hass.config_entries.async_update_entry(entry, options=merged)
    _LOGGER.debug("Inherited %s settings from the previous integration", gained)
    return True


def _adopt_devices(hass: HomeAssistant, entry: ConfigEntry, old_entry: ConfigEntry) -> None:
    """Repoint the predecessor's devices at this entry, keeping the same device rows.

    The identifiers come from `build_device_info` rather than being rebuilt here, so the
    device this leaves behind is by construction the one our platforms will look up. If
    the two ever drifted, `async_get_or_create` would quietly mint a second device and
    strand the adopted one.

    Only ever add this entry, never remove the old one. Removing it is what
    `hass.config_entries.async_remove` does anyway, and only that path is reached once
    adoption is known to be complete. Doing it here instead would fire
    `entity_registry.async_device_modified`, which deletes every entity of this device
    that is still pointing at the config entry just detached - which is to say, exactly
    the entities adoption deliberately refused to move, silently and before
    `AdoptionResult.complete` ever gets a chance to protect them.

    A predecessor entry can own more than one device (v2.0.0pre1 created a second one per
    Ecowitt channel), and only one device may hold a given identifier: passing the same
    set twice raises `DeviceIdentifierCollisionError` and would fail setup for good. So
    exactly one of them can be the device our platforms resolve, and which one must not
    be left to the order the registry happens to yield. Once the domain really changes,
    nothing holds the target identifiers yet, so a per-channel row that happened to come
    first would become the station device and every adopted entity would be moved onto
    it, stranding the real one with the user's name, area and labels on it. The device
    carrying the most entities wins instead, ties broken on `device.id` so the outcome
    does not depend on storage order at all. The others keep their own identifiers and
    are only repointed.

    A device carrying no entities is left alone entirely. Attaching this entry to it
    would keep it alive forever: `device_registry.async_cleanup` subtracts
    `references_config_entries` from the orphan set, so a device linked to any live
    config entry is never reaped, and an empty device page would sit under this
    integration for good. Left untouched, `async_remove(old_entry)` takes its last config
    entry away and deletes it. Nothing rides on it - the remove branch of
    `entity_registry.async_device_modified` only deletes entities whose `config_entry_id`
    is one of the removed device's own, and by this point the adopted ones point at this
    entry.

    That count is taken before our platforms run, so it catches a device that is already
    empty when adoption starts, but not one adoption itself empties. A predecessor still
    on v2.0.0pre1 arrives with its per-channel Ecowitt device still holding entities, so
    it reads as populated and gets this entry attached; its entities are then adopted and
    `async_forward_entry_setups` re-homes them onto the canonical device, because
    `EcowittBridge` and `WeatherSensor` both take their `device_info` from
    `build_device_info`. The row is left empty, still referenced by a live config entry,
    and `async_cleanup` therefore never reaps it. The residue is cosmetic only - the
    `entity_id` values do not change, so no history and no long-term statistics are
    involved - and it is left alone deliberately, because closing it would mean another
    pass after platform setup for a configuration that does not exist in the field.
    """

    device_registry = dr.async_get(hass)
    registry = er.async_get(hass)
    identifiers = set(build_device_info(entry)["identifiers"])

    devices = dr.async_entries_for_config_entry(device_registry, old_entry.entry_id)
    held = {
        device.id: len(er.async_entries_for_device(registry, device.id, include_disabled_entities=True))
        for device in devices
    }
    populated = [device for device in devices if held[device.id]]
    canonical = min(populated, key=lambda device: (-held[device.id], device.id), default=None)

    for device in populated:
        holder = device_registry.async_get_device(identifiers=identifiers)
        if device is not canonical or (holder is not None and holder.id != device.id):
            device_registry.async_update_device(device.id, add_config_entry_id=entry.entry_id)
            continue

        device_registry.async_update_device(
            device.id,
            new_identifiers=identifiers,  # type: ignore[arg-type]  same 1-tuple shape as build_device_info
            add_config_entry_id=entry.entry_id,
        )


async def _adopt_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    old_entry: ConfigEntry,
    result: AdoptionResult,
) -> None:
    """Move every registry entry of `old_entry` onto this integration."""

    registry = er.async_get(hass)

    for old in er.async_entries_for_config_entry(registry, old_entry.entry_id):
        # Home Assistant does not check this itself: the duplicate-unique_id guard in
        # `_async_update_entity` only runs when `new_unique_id` is passed, so changing
        # just the platform onto an already-taken key would leave two registry entries
        # sharing one index slot. Happens when a user sets this integration up fresh
        # and only then tries to adopt.
        if (clash := registry.async_get_entity_id(old.domain, DOMAIN, old.unique_id)) is not None:
            _LOGGER.warning(
                "Cannot adopt %s: unique id %r is already used by %s",
                old.entity_id,
                old.unique_id,
                clash,
            )
            result.conflicting.append(old.entity_id)
            continue

        if not _release_restored_state(hass, old.entity_id):
            _LOGGER.warning(
                "Cannot adopt %s: it still has a live state, so an integration is driving it",
                old.entity_id,
            )
            result.live.append(old.entity_id)
            continue

        registry.async_update_entity_platform(old.entity_id, DOMAIN, new_config_entry_id=entry.entry_id)
        result.adopted.append(old.entity_id)


async def async_adopt_predecessor(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    predecessor_domain: str | None = None,
) -> AdoptionResult:
    """Carry the predecessor integration's entities over to this one.

    Safe to call on every setup: with no predecessor entry left it is a dictionary
    lookup. Safe to call again after a partial run, because each entity is decided
    independently and an already-adopted one is simply no longer listed under the old
    config entry.
    """

    result = AdoptionResult()

    predecessor_domain = predecessor_domain or PREDECESSOR_DOMAIN
    if predecessor_domain == DOMAIN:
        # Nothing was renamed yet, so there is no predecessor to adopt from.
        return result

    if not (old_entries := hass.config_entries.async_entries(predecessor_domain)):
        return result

    # Normally already done by setup, before the options were read. Repeated here so a
    # caller that forgets cannot silently drop the settings - it is a no-op second time.
    inherit_predecessor_options(hass, entry, predecessor_domain=predecessor_domain)

    for old_entry in old_entries:
        if old_entry.state is ConfigEntryState.LOADED:
            # Its entities cannot be migrated while loaded, and both integrations would
            # otherwise fight over the same webhook routes. Unload rather than refuse:
            # the user is mid-migration and this entry is on its way out anyway.
            if not await hass.config_entries.async_unload(old_entry.entry_id):
                _LOGGER.error(
                    "Could not unload the previous integration (%s); adoption skipped. "
                    "Restart Home Assistant and try again",
                    old_entry.entry_id,
                )
                # Counted as left behind rather than passed over in silence. This is the
                # run where *nothing* moved, so it is also where deleting the old entry
                # by hand would cost the most - exactly what the repair notice is for.
                registry = er.async_get(hass)
                result.live.extend(
                    old.entity_id for old in er.async_entries_for_config_entry(registry, old_entry.entry_id)
                )
                continue

        # Scoped to this predecessor entry, then folded in: whether an entry may be
        # removed depends on its own entities only, never on what a sibling left behind.
        entry_result = AdoptionResult()
        await _adopt_entities(hass, entry, old_entry, entry_result)

        # Before removing the old entry, not after: `async_remove` clears the entry from
        # its devices, and a device that loses its last config entry is deleted along
        # with the entities pointing at it.
        _adopt_devices(hass, entry, old_entry)

        if entry_result.complete:
            await hass.config_entries.async_remove(old_entry.entry_id)
            entry_result.predecessor_removed = True
        else:
            # Removing the entry now would delete whatever we could not carry over.
            # Leaving it in place costs a repair notice and keeps a retry possible.
            _LOGGER.error(
                "Adopted %s entities but %s could not be moved; the previous integration "
                "is left in place so nothing is lost",
                len(entry_result.adopted),
                len(entry_result.skipped),
            )

        result.absorb(entry_result)

    if result.adopted:
        _LOGGER.info(
            "Adopted %s entities from %s; their history and statistics are unchanged",
            len(result.adopted),
            predecessor_domain,
        )

    return result


def _adoption_issue_id(entry: ConfigEntry) -> str:
    """Return the Repairs issue id for this config entry."""
    return f"predecessor_adoption_{entry.entry_id}"


def _sample_skipped(skipped: list[str]) -> str:
    """Render the stranded entities short enough to read at a glance.

    A predecessor that refuses to unload strands its whole station at once, and a WSLink
    station carries on the order of eighty sensor keys. Spelled out in full, the list
    would push the one sentence that matters - do not delete the old entry - off the
    bottom of the notice. Cut here rather than in the translations, so no language has to
    solve it again; the total travels beside it as its own placeholder.
    """

    shown = sorted(skipped)[:ISSUE_ENTITY_SAMPLE]
    if len(skipped) > len(shown):
        shown.append("...")
    return ", ".join(shown)


@callback
def update_predecessor_adoption_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
    result: AdoptionResult,
) -> None:
    """Tell the user about a migration that stalled, and what not to do about it.

    A partial run leaves the previous integration's entry in place on purpose, where it
    reads as broken ("Integration not found"). The obvious reaction - deleting it under
    Settings - is the one action that cannot be undone: it calls
    `entity_registry.async_clear_config_entry`, and the registry entries it drops are
    what the recorder history and the long-term statistics hang off. That warning leads
    the notice; the list of what is still stranded comes underneath it, sampled rather
    than spelled out.

    Cleared again as soon as a later pass finishes the job, so it cannot outlive the
    problem it describes.
    """

    issue_id = _adoption_issue_id(entry)

    if result.attempted and not result.complete:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id=issue_id,
            is_persistent=True,
            is_fixable=False,
            severity=IssueSeverity.ERROR,
            translation_key="predecessor_adoption_incomplete",
            translation_placeholders={
                "entities": _sample_skipped(result.skipped),
                "count": str(len(result.skipped)),
            },
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id=issue_id)
