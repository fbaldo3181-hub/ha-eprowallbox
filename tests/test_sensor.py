"""Tests for eProWallbox sensor and binary sensor platforms."""

from __future__ import annotations

import pytest

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import FakeModbusClient

pytestmark = pytest.mark.usefixtures("init_integration")


def _sensor(key: str) -> str:
    return f"sensor.eprowallbox_{key}"


def _binary(key: str) -> str:
    return f"binary_sensor.eprowallbox_{key}"


async def test_entity_counts(hass: HomeAssistant) -> None:
    """All Modbus sensors and binary sensors are created."""
    assert len(hass.states.async_entity_ids("sensor")) == 43
    # 7 capteurs binaires Modbus + le capteur de connectivité
    assert len(hass.states.async_entity_ids("binary_sensor")) == 8


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("general_status", 5),
        ("ocpp_status", 2),
        ("actual_error", 0),
        ("hw_current_limit", 16.0),  # mA -> A
        ("current_limit", 10.0),
        ("fallback_current", 6.0),
        ("charge_time", 3600),
        ("voltage_l1", 231.5),  # mV -> V
        ("voltage_l3", 232.5),
        ("current_l2", 10.5),
        ("active_power_l3", 2500.0),
        ("active_energy_l1", 1000.5),
        ("temperature", 40.0),  # K -> °C
    ],
)
async def test_sensor_value(hass: HomeAssistant, key: str, expected: float) -> None:
    """Sensors apply the scale / offset of the Modbus configuration."""
    state = hass.states.get(_sensor(key))
    assert state is not None
    assert float(state.state) == pytest.approx(expected, abs=0.01)


async def test_sensor_string_value(hass: HomeAssistant) -> None:
    """String registers are reported as text."""
    assert hass.states.get(_sensor("serial_number")).state == "EPW1234567890"
    assert hass.states.get(_sensor("firmware_version")).state == "1.2.3"


async def test_sensor_attributes(hass: HomeAssistant) -> None:
    """Units, device classes and state classes come from the descriptions."""
    voltage = hass.states.get(_sensor("voltage_l1"))
    assert voltage.attributes["unit_of_measurement"] == "V"
    assert voltage.attributes["device_class"] == "voltage"
    assert voltage.attributes["state_class"] == "measurement"

    energy = hass.states.get(_sensor("active_energy_l1"))
    assert energy.attributes["unit_of_measurement"] == "Wh"
    assert energy.attributes["state_class"] == "total_increasing"

    reactive = hass.states.get(_sensor("reactive_power_l1"))
    assert reactive.attributes["unit_of_measurement"] == "var"


async def test_sensor_unique_id(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, init_integration: MockConfigEntry
) -> None:
    """Sensor entities have the expected unique_id format."""
    entity = entity_registry.async_get(_sensor("general_status"))
    assert entity is not None
    assert entity.unique_id == f"{init_integration.entry_id}_general_status"


async def test_sensor_entity_category(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Identification and parameter sensors are diagnostic entities."""
    assert (
        entity_registry.async_get(_sensor("serial_number")).entity_category
        == EntityCategory.DIAGNOSTIC
    )
    assert (
        entity_registry.async_get(_sensor("thd_voltage_l1")).entity_category
        == EntityCategory.DIAGNOSTIC
    )
    assert entity_registry.async_get(_sensor("voltage_l1")).entity_category is None


async def test_sensor_device(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """All entities share one device."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(
        identifiers={("eprowallbox", init_integration.entry_id)}
    )
    assert device is not None
    assert device.manufacturer == "eProWallbox"
    entries = er.async_entries_for_device(entity_registry, device.id)
    # 43 capteurs + 8 capteurs binaires + 1 switch + 1 number
    assert len(entries) == 53


async def test_sensors_unavailable_when_update_fails(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """Entities become unavailable when the wallbox stops answering."""
    coordinator = init_integration.runtime_data.coordinator
    mock_modbus.connection_lost = True
    coordinator._next_due.clear()

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(_sensor("general_status")).state == "unavailable"
    # Le capteur de connectivité reste disponible et passe à "off"
    assert hass.states.get(_binary("status")).state == "off"


# ---------------------------------------------------------------------------
# Binary sensors
# ---------------------------------------------------------------------------


async def test_binary_sensor_online(hass: HomeAssistant) -> None:
    """The connectivity binary sensor is on when the coordinator succeeds."""
    state = hass.states.get(_binary("status"))
    assert state is not None
    assert state.state == "on"
    assert state.attributes["device_class"] == "connectivity"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("temperature_derating", "on"),  # registre 40108 = 1
        ("dpm_limiting", "off"),  # registre 40107 = 0
        ("load_unbalance_limiting", "off"),
        ("dpm_enabled", "on"),
        ("mid_meter_enabled", "off"),  # registre 40401 = 2 -> bit 0 à 0
        ("load_unbalance_enabled", "off"),
        ("watchdog_enabled", "on"),
    ],
)
async def test_binary_sensor_state(hass: HomeAssistant, key: str, expected: str) -> None:
    """Binary sensors report bit 0 of their register."""
    state = hass.states.get(_binary(key))
    assert state is not None
    assert state.state == expected


async def test_binary_sensor_attributes(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Derating is a problem sensor, enabled flags are diagnostic."""
    assert hass.states.get(_binary("temperature_derating")).attributes["device_class"] == "problem"
    assert (
        entity_registry.async_get(_binary("dpm_enabled")).entity_category
        == EntityCategory.DIAGNOSTIC
    )


async def test_binary_sensor_follows_register(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """A register change is reflected after the next read."""
    coordinator = init_integration.runtime_data.coordinator
    mock_modbus.memory[40108] = 0
    coordinator._next_due["temperature_derating"] = 0

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(_binary("temperature_derating")).state == "off"
