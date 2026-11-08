"""Tests for the setup of the eProWallbox integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eprowallbox.const import (
    DOMAIN,
    FRONTEND_SCRIPT_URL,
    FRONTEND_VERSION,
)

from .conftest import FakeModbusClient


async def test_setup_and_unload(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """The entry loads, then unloads and closes the Modbus connection."""
    entry = init_integration
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.coordinator.last_update_success
    assert mock_modbus.connected

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert mock_modbus.closed


async def test_setup_retry_when_wallbox_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """An unreachable wallbox makes Home Assistant retry the setup later."""
    mock_modbus.connect_ok = False
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_card_is_served_and_loaded(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_frontend: MagicMock,
) -> None:
    """The Lovelace card is exposed as a static path and loaded on dashboards."""
    hass.http.async_register_static_paths.assert_called_once()
    (configs,) = hass.http.async_register_static_paths.call_args.args
    assert [config.url_path for config in configs] == [FRONTEND_SCRIPT_URL]
    assert Path(configs[0].path).is_file()

    mock_frontend.assert_called_once_with(
        hass, f"{FRONTEND_SCRIPT_URL}?v={FRONTEND_VERSION}"
    )


async def test_all_platforms_loaded(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Every platform adds its entities (a platform file copied by mistake would not)."""
    assert len(hass.states.async_entity_ids("sensor")) == 43
    assert len(hass.states.async_entity_ids("binary_sensor")) == 8
    assert len(hass.states.async_entity_ids("switch")) == 1
    assert len(hass.states.async_entity_ids("number")) == 1
    assert DOMAIN == "eprowallbox"
