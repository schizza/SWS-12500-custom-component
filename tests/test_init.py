"""Integration init tests using Home Assistant pytest fixtures.

These tests rely on `pytest-homeassistant-custom-component` to provide:
- `hass` fixture (running Home Assistant instance)
- `MockConfigEntry` helper for config entries

They validate that the integration can set up a config entry and that the
coordinator is stored on `entry.runtime_data`.

Note:
This integration registers aiohttp routes via `hass.http.app.router`. In this
test environment, `hass.http` may not be set up, so we patch route registration
to keep these tests focused on setup logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sws12500 import (
    CONFIG_ENTRY_VERSION,
    WeatherDataUpdateCoordinator,
    async_migrate_entry,
    async_setup_entry,
)
from custom_components.sws12500.config_flow import ConfigFlowHandler
from custom_components.sws12500.const import (
    DOMAIN,
    POCASI_CZ_ENABLED,
    POCASI_CZ_ENABLED_LEGACY,
    WINDY_ENABLED,
)
from custom_components.sws12500.data import SWSRuntimeData
from homeassistant.util import dt as dt_util


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Create a minimal config entry for the integration."""
    return MockConfigEntry(domain=DOMAIN, data={}, options={})


async def test_async_setup_entry_creates_runtime_state(
    hass, config_entry: MockConfigEntry, monkeypatch
):
    """Setting up a config entry should succeed and populate runtime state."""
    config_entry.add_to_hass(hass)

    # `async_setup_entry` calls `register_path`, which needs `hass.http`.
    # Patch it out so the test doesn't depend on aiohttp being initialized.
    monkeypatch.setattr(
        "custom_components.sws12500.register_path",
        lambda _hass, _coordinator, _coordinator_h, _entry: True,
    )

    # Calling async_setup_entry directly leaves the entry in NOT_LOADED state, so the
    # health coordinator's first refresh (which requires SETUP_IN_PROGRESS and does
    # network I/O) is mocked out to keep this test focused on setup wiring.
    monkeypatch.setattr(
        "custom_components.sws12500.HealthCoordinator.async_config_entry_first_refresh",
        AsyncMock(return_value=None),
    )

    # Avoid depending on Home Assistant integration loader in this test.
    # This keeps the test focused on our integration's setup behavior.
    monkeypatch.setattr(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=True),
    )

    result = await async_setup_entry(hass, config_entry)
    assert result is True

    # Per-entry state now lives on entry.runtime_data (SWSRuntimeData), not in
    # hass.data[DOMAIN][entry_id]. hass.data[DOMAIN] only holds shared route state.
    assert DOMAIN in hass.data
    assert isinstance(config_entry.runtime_data, SWSRuntimeData)
    assert config_entry.runtime_data.coordinator is not None
    assert config_entry.runtime_data.health_coordinator is not None


async def test_async_setup_entry_forwards_sensor_platform(
    hass, config_entry: MockConfigEntry, monkeypatch
):
    """The integration should forward entry setups to the sensor platform."""
    config_entry.add_to_hass(hass)

    # `async_setup_entry` calls `register_path`, which needs `hass.http`.
    # Patch it out so the test doesn't depend on aiohttp being initialized.
    monkeypatch.setattr(
        "custom_components.sws12500.register_path",
        lambda _hass, _coordinator, _coordinator_h, _entry: True,
    )

    # Calling async_setup_entry directly leaves the entry in NOT_LOADED state, so the
    # health coordinator's first refresh (which requires SETUP_IN_PROGRESS and does
    # network I/O) is mocked out to keep this test focused on setup wiring.
    monkeypatch.setattr(
        "custom_components.sws12500.HealthCoordinator.async_config_entry_first_refresh",
        AsyncMock(return_value=None),
    )

    # Patch forwarding so we don't need to load real platforms for this unit/integration test.
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

    result = await async_setup_entry(hass, config_entry)
    assert result is True

    hass.config_entries.async_forward_entry_setups.assert_awaited()
    forwarded_entry, forwarded_platforms = (
        hass.config_entries.async_forward_entry_setups.await_args.args
    )
    assert forwarded_entry.entry_id == config_entry.entry_id
    assert "sensor" in list(forwarded_platforms)


async def test_weather_data_update_coordinator_can_be_constructed(
    hass, config_entry: MockConfigEntry
):
    """Coordinator should be constructible with a real hass fixture."""
    coordinator = WeatherDataUpdateCoordinator(hass, config_entry)
    assert coordinator.hass is hass
    assert coordinator.config is config_entry


async def test_check_stale_callback_runs_update(
    hass, config_entry: MockConfigEntry, monkeypatch
):
    """The hourly _check_stale callback registered during setup runs the stale check."""
    config_entry.add_to_hass(hass)

    monkeypatch.setattr(
        "custom_components.sws12500.register_path",
        lambda _hass, _coordinator, _coordinator_h, _entry: True,
    )
    monkeypatch.setattr(
        "custom_components.sws12500.HealthCoordinator.async_config_entry_first_refresh",
        AsyncMock(return_value=None),
    )
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

    # Capture the time-interval callback async_setup_entry registers.
    captured: dict = {}

    def _capture(_hass, action, _interval):
        captured["cb"] = action
        return lambda: None

    monkeypatch.setattr("custom_components.sws12500.async_track_time_interval", _capture)

    stale = MagicMock()
    monkeypatch.setattr("custom_components.sws12500.update_stale_sensors_issue", stale)

    assert await async_setup_entry(hass, config_entry) is True
    assert "cb" in captured

    captured["cb"](dt_util.utcnow())
    stale.assert_called_once_with(hass, config_entry)


def test_config_flow_version_matches_migration_target() -> None:
    """The flow version and the migration target must not drift apart."""
    assert ConfigFlowHandler.VERSION == CONFIG_ENTRY_VERSION


async def test_migrate_moves_legacy_pocasi_key(hass) -> None:
    """A v1 entry carrying the misspelled key migrates to v2 keeping the value."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={POCASI_CZ_ENABLED_LEGACY: True, WINDY_ENABLED: True},
        version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 2
    assert entry.options[POCASI_CZ_ENABLED] is True
    assert POCASI_CZ_ENABLED_LEGACY not in entry.options
    # Unrelated options survive untouched.
    assert entry.options[WINDY_ENABLED] is True


async def test_migrate_without_pocasi_option(hass) -> None:
    """An entry that never had the Pocasi option migrates cleanly."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={WINDY_ENABLED: False}, version=1)
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 2
    assert POCASI_CZ_ENABLED not in entry.options
    assert entry.options[WINDY_ENABLED] is False


async def test_migrate_does_not_clobber_correct_key(hass) -> None:
    """When both keys are present, the already-correct one wins."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={POCASI_CZ_ENABLED_LEGACY: False, POCASI_CZ_ENABLED: True},
        version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.options[POCASI_CZ_ENABLED] is True
    assert POCASI_CZ_ENABLED_LEGACY not in entry.options


async def test_migrate_is_idempotent(hass) -> None:
    """Running the migration twice leaves the entry unchanged."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={}, options={POCASI_CZ_ENABLED_LEGACY: True}, version=1
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    first = dict(entry.options)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 2
    assert dict(entry.options) == first
    assert entry.options[POCASI_CZ_ENABLED] is True


async def test_migrate_refuses_future_version(hass) -> None:
    """An entry written by a newer version is not downgraded."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={}, options={}, version=CONFIG_ENTRY_VERSION + 1
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is False
    assert entry.version == CONFIG_ENTRY_VERSION + 1
