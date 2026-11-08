"""Tests for eProWallbox number platform."""

from __future__ import annotations

import pytest

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import FakeModbusClient

NUMBER = "number.eprowallbox_current_limit_setpoint"

pytestmark = pytest.mark.usefixtures("init_integration")


async def test_number_state(hass: HomeAssistant) -> None:
    """The number shows the setpoint in amperes (40407 = 10000 mA)."""
    state = hass.states.get(NUMBER)
    assert state is not None
    assert float(state.state) == pytest.approx(10.0)
    assert state.attributes["unit_of_measurement"] == "A"
    assert state.attributes["device_class"] == "current"
    assert state.attributes["mode"] == "slider"


async def test_number_range_follows_hardware_limit(hass: HomeAssistant) -> None:
    """The maximum is the hardware limit read from the wallbox (16 A)."""
    state = hass.states.get(NUMBER)
    assert state.attributes["min"] == 6
    assert state.attributes["max"] == pytest.approx(16.0)
    assert state.attributes["step"] == 1


async def test_number_unique_id(
    entity_registry: er.EntityRegistry, init_integration: MockConfigEntry
) -> None:
    """The number has the expected unique_id."""
    entity = entity_registry.async_get(NUMBER)
    assert entity is not None
    assert entity.unique_id == f"{init_integration.entry_id}_current_limit_setpoint"


async def test_number_set_value(
    hass: HomeAssistant, mock_modbus: FakeModbusClient
) -> None:
    """Setting 12 A writes 12000 mA on the two 32-bit registers."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {"entity_id": NUMBER, ATTR_VALUE: 12},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert mock_modbus.writes == [(40407, [0, 12000])]
    assert float(hass.states.get(NUMBER).state) == pytest.approx(12.0)


async def test_number_set_value_out_of_range(
    hass: HomeAssistant, mock_modbus: FakeModbusClient
) -> None:
    """A value above the hardware limit is rejected without writing."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {"entity_id": NUMBER, ATTR_VALUE: 20},
            blocking=True,
        )

    assert mock_modbus.writes == []


async def test_number_write_error(
    hass: HomeAssistant, mock_modbus: FakeModbusClient
) -> None:
    """A refused write is reported to the caller."""
    mock_modbus.fail_writes = True

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {"entity_id": NUMBER, ATTR_VALUE: 8},
            blocking=True,
        )

    assert float(hass.states.get(NUMBER).state) == pytest.approx(10.0)
