"""Legacy (PWS/WSLink) and Ecowitt must never run at the same time.

Both endpoints remap onto the same internal sensor keys and push through the same
coordinator, so running both mixes measurement units, blanks the keys the other protocol
does not report, and feeds one entity from two sources.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sws12500.conflicts import (
    ERROR_MUTUALLY_EXCLUSIVE,
    effective_protocols,
    protocols_conflict,
    update_protocol_conflict_issue,
)
from custom_components.sws12500.const import (
    API_ID,
    API_KEY,
    DOMAIN,
    ECOWITT_ENABLED,
    ECOWITT_WEBHOOK_ID,
    LEGACY_ENABLED,
    WSLINK,
)
from homeassistant.helpers import issue_registry as ir


def _entry(**options: Any) -> Any:
    return SimpleNamespace(options=options, entry_id="entry123")


# ---------------------------------------------------------------------------
# effective_protocols / protocols_conflict
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        # LEGACY_ENABLED defaults to True, ECOWITT_ENABLED to False.
        ({}, (True, False)),
        ({LEGACY_ENABLED: True, ECOWITT_ENABLED: False}, (True, False)),
        ({LEGACY_ENABLED: False, ECOWITT_ENABLED: True}, (False, True)),
        ({LEGACY_ENABLED: False, ECOWITT_ENABLED: False}, (False, False)),
        # Conflict: legacy wins, Ecowitt is dropped rather than corrupting entities.
        ({LEGACY_ENABLED: True, ECOWITT_ENABLED: True}, (True, False)),
        # A bare ECOWITT_ENABLED still conflicts, because legacy defaults to on.
        ({ECOWITT_ENABLED: True}, (True, False)),
    ],
)
def test_effective_protocols(options, expected) -> None:
    assert effective_protocols(_entry(**options)) == expected


@pytest.mark.parametrize(
    ("options", "conflict"),
    [
        ({}, False),
        ({LEGACY_ENABLED: False, ECOWITT_ENABLED: True}, False),
        ({LEGACY_ENABLED: True, ECOWITT_ENABLED: True}, True),
        ({ECOWITT_ENABLED: True}, True),
    ],
)
def test_protocols_conflict(options, conflict) -> None:
    assert protocols_conflict(_entry(**options)) is conflict


# ---------------------------------------------------------------------------
# Repairs issue
# ---------------------------------------------------------------------------


async def test_conflict_issue_created_and_cleared(hass) -> None:
    """The issue appears for a conflicting entry and disappears once resolved."""
    registry = ir.async_get(hass)
    entry = _entry(**{LEGACY_ENABLED: True, ECOWITT_ENABLED: True})

    update_protocol_conflict_issue(hass, entry)
    issue = registry.async_get_issue(DOMAIN, f"protocol_conflict_{entry.entry_id}")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.ERROR
    assert issue.translation_key == "protocol_conflict"

    entry.options = {LEGACY_ENABLED: True, ECOWITT_ENABLED: False}
    update_protocol_conflict_issue(hass, entry)
    assert registry.async_get_issue(DOMAIN, f"protocol_conflict_{entry.entry_id}") is None


async def test_no_issue_for_clean_entry(hass) -> None:
    """A single-protocol entry raises nothing."""
    registry = ir.async_get(hass)
    entry = _entry(**{LEGACY_ENABLED: False, ECOWITT_ENABLED: True})

    update_protocol_conflict_issue(hass, entry)
    assert registry.async_get_issue(DOMAIN, f"protocol_conflict_{entry.entry_id}") is None


# ---------------------------------------------------------------------------
# Options flow guards
# ---------------------------------------------------------------------------


async def test_options_basic_rejects_enabling_legacy_while_ecowitt_on(hass, enable_custom_integrations) -> None:
    """Turning the legacy endpoint on while Ecowitt is active is refused."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={LEGACY_ENABLED: False, ECOWITT_ENABLED: True, ECOWITT_WEBHOOK_ID: "abc"},
    )
    entry.add_to_hass(hass)

    init = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(init["flow_id"], user_input={"next_step_id": "basic"})

    result = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={
            API_ID: "station",
            API_KEY: "secret",
            WSLINK: False,
            LEGACY_ENABLED: True,
        },
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": ERROR_MUTUALLY_EXCLUSIVE}
    # Nothing was written.
    assert entry.options[ECOWITT_ENABLED] is True
    assert entry.options[LEGACY_ENABLED] is False


async def test_options_ecowitt_rejects_enabling_while_legacy_on(hass, enable_custom_integrations) -> None:
    """Turning Ecowitt on while the legacy endpoint is active is refused."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={LEGACY_ENABLED: True, ECOWITT_ENABLED: False, API_ID: "a", API_KEY: "b"},
    )
    entry.add_to_hass(hass)

    init = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        init["flow_id"], user_input={"next_step_id": "ecowitt"}
    )
    webhook = (form.get("description_placeholders") or {})["webhook_id"]

    result = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={ECOWITT_WEBHOOK_ID: webhook, ECOWITT_ENABLED: True},
    )

    assert result["type"] == "form"
    assert result["step_id"] == "ecowitt"
    assert result["errors"] == {"base": ERROR_MUTUALLY_EXCLUSIVE}
    assert entry.options[ECOWITT_ENABLED] is False


async def test_options_ecowitt_allows_saving_while_disabled(hass, enable_custom_integrations) -> None:
    """The guard only blocks *enabling* it - editing the webhook id stays possible."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={LEGACY_ENABLED: True, ECOWITT_ENABLED: False, API_ID: "a", API_KEY: "b"},
    )
    entry.add_to_hass(hass)

    init = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(init["flow_id"], user_input={"next_step_id": "ecowitt"})

    result = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={ECOWITT_WEBHOOK_ID: "deadbeef", ECOWITT_ENABLED: False},
    )

    assert result["type"] == "create_entry"
    assert result["data"][ECOWITT_WEBHOOK_ID] == "deadbeef"


# ---------------------------------------------------------------------------
# Route wiring
# ---------------------------------------------------------------------------


async def test_conflicting_entry_does_not_wire_ecowitt_route(hass, enable_custom_integrations) -> None:
    """A pre-existing both-enabled config must not ingest Ecowitt payloads.

    Without this the Ecowitt handler keeps writing imperial values into the same
    coordinator as the legacy endpoint, mislabelling units and blanking the keys the
    other protocol reports.
    """

    class _Router:
        def add_get(self, path: str, handler: Any, **_kw: Any) -> Any:
            return SimpleNamespace(method="GET")

        def add_post(self, path: str, handler: Any, **_kw: Any) -> Any:
            return SimpleNamespace(method="POST")

    hass.http = SimpleNamespace(app=SimpleNamespace(router=_Router()))

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            LEGACY_ENABLED: True,
            ECOWITT_ENABLED: True,
            ECOWITT_WEBHOOK_ID: "abc",
            API_ID: "a",
            API_KEY: "b",
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    routes = hass.data[DOMAIN]["routes"]
    snapshot = routes.snapshot()

    ecowitt = [r for r in snapshot.values() if r["path"].startswith("/weatherhub/")]
    assert ecowitt, "ecowitt route should be registered"
    assert all(not r["enabled"] for r in ecowitt), "ecowitt must be inactive while legacy is on"

    # The legacy (WU) route is the one that stays live.
    assert routes.path_enabled("/weatherstation/updateweatherstation.php")

    # ... and the user is told about it.
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"protocol_conflict_{entry.entry_id}") is not None
