"""Tests for eProWallbox coordinator."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eprowallbox.coordinator import (
    REGISTERS,
    SLAVE_ID,
    Register,
    TemplateCoordinator,
    _decode,
)

from .conftest import FakeModbusClient


async def test_coordinator_update(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """Test a successful first refresh reads and decodes every register."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TemplateCoordinator(hass, mock_config_entry)
    await coordinator.async_refresh()

    assert coordinator.last_update_success
    data = coordinator.data
    assert len(data) == len(REGISTERS) == 51

    # string, uint16, uint32, float32
    assert data["serial_number"] == "EPW1234567890"
    assert data["firmware_version"] == "1.2.3"
    assert data["general_status"] == 5
    assert data["hw_current_limit"] == 16000
    assert data["current_limit"] == 10000
    assert data["voltage_l1"] == pytest.approx(231500.0)
    assert data["voltage_l3"] == pytest.approx(232500.0)
    assert data["temperature"] == pytest.approx(313.15, abs=0.01)
    assert data["active_power_l2"] == pytest.approx(2400.0)
    assert data["charging_enabled"] == 1

    # Connexion ouverte avec l'esclave configuré
    assert mock_modbus.connected
    assert {read[2] for read in mock_modbus.reads} == {SLAVE_ID}


async def test_coordinator_keys_are_unique() -> None:
    """Every register has a unique key and a unique address."""
    keys = [register.key for register in REGISTERS]
    addresses = [register.address for register in REGISTERS]
    assert len(keys) == len(set(keys))
    assert len(addresses) == len(set(addresses))


async def test_coordinator_respects_scan_intervals(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """Registers are only read again once their own interval has elapsed."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TemplateCoordinator(hass, mock_config_entry)
    await coordinator.async_refresh()
    assert len(mock_modbus.reads) == len(REGISTERS)

    # Rafraîchissement immédiat : rien n'est dû, les valeurs sont conservées
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert len(mock_modbus.reads) == len(REGISTERS)
    assert coordinator.data["general_status"] == 5

    # Un seul registre arrive à échéance
    mock_modbus.memory[40101] = 4
    coordinator._next_due["general_status"] = 0
    await coordinator.async_refresh()
    assert len(mock_modbus.reads) == len(REGISTERS) + 1
    assert mock_modbus.reads_of(40101) == 2
    assert coordinator.data["general_status"] == 4


async def test_coordinator_connect_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """A refused connection makes the update fail."""
    mock_config_entry.add_to_hass(hass)
    mock_modbus.connect_ok = False
    coordinator = TemplateCoordinator(hass, mock_config_entry)

    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert mock_modbus.reads == []


async def test_coordinator_all_reads_refused_on_first_refresh(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """The first refresh fails when no register can be read at all."""
    mock_config_entry.add_to_hass(hass)
    mock_modbus.fail_all_reads = True
    coordinator = TemplateCoordinator(hass, mock_config_entry)

    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert isinstance(coordinator.last_exception, UpdateFailed)


async def test_coordinator_connection_lost(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """The update fails when the wallbox stops answering, then recovers."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TemplateCoordinator(hass, mock_config_entry)
    await coordinator.async_refresh()
    assert coordinator.last_update_success

    mock_modbus.connection_lost = True
    coordinator._next_due["general_status"] = 0
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert isinstance(coordinator.last_exception, UpdateFailed)

    mock_modbus.connection_lost = False
    coordinator._next_due["general_status"] = 0
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert coordinator.data["general_status"] == 5


async def test_coordinator_partial_read_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """An unreadable register does not stop the others."""
    mock_config_entry.add_to_hass(hass)
    mock_modbus.fail_addresses = {40101}
    coordinator = TemplateCoordinator(hass, mock_config_entry)

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert "general_status" not in coordinator.data
    assert coordinator.data["ocpp_status"] == 2
    assert len(coordinator.data) == len(REGISTERS) - 1


async def test_coordinator_keeps_last_value_on_read_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """A later read error on one register keeps its previous value."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TemplateCoordinator(hass, mock_config_entry)
    await coordinator.async_refresh()

    mock_modbus.fail_addresses = {40101}
    coordinator._next_due["general_status"] = 0
    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data["general_status"] == 5


async def test_write_register(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """Writing one register uses a single write and schedules its read-back."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TemplateCoordinator(hass, mock_config_entry)
    await coordinator.async_refresh()

    await coordinator.async_write_register(40406, 0)

    assert mock_modbus.writes == [(40406, [0])]
    assert coordinator._next_due["charging_enabled"] == 0

    await coordinator.async_refresh()
    assert coordinator.data["charging_enabled"] == 0


async def test_write_registers(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """Writing a 32-bit value writes both registers and schedules the read-back."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TemplateCoordinator(hass, mock_config_entry)
    await coordinator.async_refresh()

    await coordinator.async_write_registers(40407, [0, 12000])

    assert mock_modbus.writes == [(40407, [0, 12000])]
    assert coordinator._next_due["current_limit"] == 0
    await coordinator.async_refresh()
    assert coordinator.data["current_limit"] == 12000


async def test_write_refused(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """A refused write raises HomeAssistantError."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TemplateCoordinator(hass, mock_config_entry)
    await coordinator.async_refresh()
    mock_modbus.fail_writes = True

    with pytest.raises(HomeAssistantError):
        await coordinator.async_write_register(40406, 0)


async def test_write_connection_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """A write while the wallbox is unreachable raises HomeAssistantError."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TemplateCoordinator(hass, mock_config_entry)
    mock_modbus.connect_ok = False

    with pytest.raises(HomeAssistantError):
        await coordinator.async_write_register(40406, 1)


async def test_shutdown_closes_connection(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> None:
    """Shutting down the coordinator closes the Modbus connection."""
    mock_config_entry.add_to_hass(hass)
    coordinator = TemplateCoordinator(hass, mock_config_entry)
    await coordinator.async_refresh()

    await coordinator.async_shutdown()

    assert mock_modbus.closed


@pytest.mark.parametrize(
    ("register", "words", "expected"),
    [
        (Register("a", 0, "uint16"), [42], 42),
        (Register("a", 0, "uint32"), [0x0001, 0x0002], 65538),
        (Register("a", 0, "uint32"), [0, 16000], 16000),
        (Register("a", 0, "float32"), [0x3FC0, 0x0000], 1.5),
        (Register("a", 0, "string", count=3), [0x4142, 0x4300, 0x0000], "ABC"),
        (Register("a", 0, "string", count=2), [0x2020, 0x4142], "AB"),
    ],
)
def test_decode(register: Register, words: list[int], expected) -> None:
    """Registers are decoded big-endian."""
    assert _decode(register, words) == expected


def test_decode_nan_is_none() -> None:
    """A NaN float32 is reported as no value."""
    assert _decode(Register("a", 0, "float32"), [0x7FC0, 0x0000]) is None


def test_decode_unknown_type() -> None:
    """An unsupported data type is rejected."""
    with pytest.raises(ValueError):
        _decode(Register("a", 0, "int8"), [1])
