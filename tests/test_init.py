"""Integration init tests using Home Assistant pytest fixtures.

These tests rely on `pytest-homeassistant-custom-component` to provide:
- `hass` fixture (running Home Assistant instance)
- `MockConfigEntry` helper for config entries

They validate that the integration can set up a config entry and that the
coordinator is created and stored in `hass.data`.

Note:
This integration registers aiohttp routes via `hass.http.app.router`. In this
test environment, `hass.http` may not be set up, so we patch route registration
to keep these tests focused on setup logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sws12500 import WeatherDataUpdateCoordinator, async_setup_entry
from custom_components.sws12500.const import DOMAIN
from custom_components.sws12500.data import SWSRuntimeData


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Create a minimal config entry for the integration."""
    return MockConfigEntry(domain=DOMAIN, data={}, options={})


async def test_async_setup_entry_creates_runtime_state(
    hass, config_entry: MockConfigEntry, monkeypatch
):
    """Setting up a config entry should succeed and populate hass.data."""
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
