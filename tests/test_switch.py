"""Tests for eProWallbox switch platform."""

from __future__ import annotations

import pytest

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import FakeModbusClient

SWITCH = "switch.eprowallbox_charging_enabled"

pytestmark = pytest.mark.usefixtures("init_integration")


async def test_switch_state(hass: HomeAssistant) -> None:
    """The switch reflects the charging register (40406 = 1)."""
    state = hass.states.get(SWITCH)
    assert state is not None
    assert state.state == "on"


async def test_switch_unique_id(
    entity_registry: er.EntityRegistry, init_integration: MockConfigEntry
) -> None:
    """The switch has the expected unique_id."""
    entity = entity_registry.async_get(SWITCH)
    assert entity is not None
    assert entity.unique_id == f"{init_integration.entry_id}_charging_enabled"


async def test_switch_turn_off(
    hass: HomeAssistant, mock_modbus: FakeModbusClient
) -> None:
    """Turning the switch off writes 0 to register 40406 and reads it back."""
    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {"entity_id": SWITCH}, blocking=True
    )
    await hass.async_block_till_done()

    assert mock_modbus.writes == [(40406, [0])]
    assert hass.states.get(SWITCH).state == "off"


async def test_switch_turn_on(
    hass: HomeAssistant, mock_modbus: FakeModbusClient
) -> None:
    """Turning the switch on writes 1 to register 40406."""
    mock_modbus.memory[40406] = 0
    coordinator = hass.config_entries.async_entries("eprowallbox")[0].runtime_data.coordinator
    coordinator._next_due["charging_enabled"] = 0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == "off"

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_ON, {"entity_id": SWITCH}, blocking=True
    )
    await hass.async_block_till_done()

    assert mock_modbus.writes == [(40406, [1])]
    assert hass.states.get(SWITCH).state == "on"


async def test_switch_write_error(
    hass: HomeAssistant, mock_modbus: FakeModbusClient
) -> None:
    """A refused write is reported to the caller and the state is unchanged."""
    mock_modbus.fail_writes = True

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_OFF, {"entity_id": SWITCH}, blocking=True
        )

    assert hass.states.get(SWITCH).state == "on"
