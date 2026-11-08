"""Common fixtures for the eProWallbox tests."""

from __future__ import annotations

from collections.abc import Generator
import struct
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymodbus.exceptions import ConnectionException

from homeassistant.const import CONF_HOST, CONF_PORT

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eprowallbox.const import DOMAIN

# ---------------------------------------------------------------------------
# Register image of a fake wallbox
# ---------------------------------------------------------------------------


def float_words(value: float) -> list[int]:
    """Encode a float32 as two big-endian 16-bit registers."""
    high, low = struct.unpack(">HH", struct.pack(">f", value))
    return [high, low]


def uint32_words(value: int) -> list[int]:
    """Encode a uint32 as two big-endian 16-bit registers."""
    return [(value >> 16) & 0xFFFF, value & 0xFFFF]


def string_words(text: str, count: int) -> list[int]:
    """Encode a string on `count` 16-bit registers (zero padded)."""
    raw = text.encode("ascii").ljust(count * 2, b"\x00")
    return list(struct.unpack(f">{count}H", raw))


def default_memory() -> dict[int, int]:
    """Return the register image of a wallbox charging at ~7 kW."""
    memory: dict[int, int] = {}

    def put(address: int, words: list[int]) -> None:
        for offset, word in enumerate(words):
            memory[address + offset] = word

    # Identification
    put(40000, string_words("EPW1234567890", 8))
    put(40008, string_words("1.2.3", 4))
    put(40012, string_words("2.0", 4))
    put(40017, [1])
    put(40018, uint32_words(16000))
    # États
    put(40100, [0])
    put(40101, [5])  # C2 - charging
    put(40102, [2])  # OCPP Charging
    put(40103, uint32_words(16000))
    # Binary sensors (bit 0)
    put(40106, [0])
    put(40107, [0])
    put(40108, [1])  # temperature derating active
    put(40400, [1])
    put(40401, [2])  # bit 0 clear -> off
    put(40402, [0])
    put(40412, [1])
    # Paramètres
    put(40403, uint32_words(6000))
    put(40406, [1])  # charging enabled
    put(40407, uint32_words(10000))  # 10 A
    put(40409, uint32_words(6000))
    put(40411, [0])
    put(40413, [60])
    # Session / température
    put(40600, uint32_words(3600))
    put(40602, float_words(313.15))  # 40 °C
    # Mesures par phase
    for index in range(3):
        put(40604 + 2 * index, float_words(231500.0 + 500 * index))  # mV
        put(40610 + 2 * index, float_words(2.5))
        put(40620 + 2 * index, float_words(10.25 + 0.25 * index))
        put(40626 + 2 * index, float_words(3.5))
        put(40636 + 2 * index, float_words(2300.0 + 100 * index))
        put(40642 + 2 * index, float_words(100.0))
        put(40648 + 2 * index, float_words(2310.0))
        put(40658 + 2 * index, float_words(1000.5))
        put(40664 + 2 * index, float_words(50.0))
    return memory


# ---------------------------------------------------------------------------
# Fake pymodbus client
# ---------------------------------------------------------------------------


class FakeResponse:
    """Minimal pymodbus response."""

    def __init__(self, registers: list[int] | None = None, error: bool = False) -> None:
        """Initialize the response."""
        self.registers = registers or []
        self._error = error

    def isError(self) -> bool:  # noqa: N802 - name imposed by pymodbus
        """Return True for an error / exception response."""
        return self._error


class FakeModbusClient:
    """Stand-in for pymodbus.client.AsyncModbusTcpClient.

    The signatures use `device_id`, like pymodbus >= 3.10.
    """

    def __init__(self) -> None:
        """Initialize the fake wallbox."""
        self.memory: dict[int, int] = default_memory()
        self.connected = False
        self.connect_ok = True
        self.fail_all_reads = False
        self.fail_addresses: set[int] = set()
        self.fail_writes = False
        self.connection_lost = False
        self.reads: list[tuple[int, int, int]] = []
        self.writes: list[tuple[int, list[int]]] = []
        self.closed = False

    async def connect(self) -> bool:
        """Open the (fake) connection."""
        self.connected = self.connect_ok
        return self.connect_ok

    def close(self) -> None:
        """Close the (fake) connection."""
        self.connected = False
        self.closed = True

    async def read_holding_registers(
        self, address: int, *, count: int = 1, device_id: int = 1
    ) -> FakeResponse:
        """Read registers from the fake memory."""
        self.reads.append((address, count, device_id))
        if self.connection_lost:
            raise ConnectionException("Connection lost")
        if self.fail_all_reads or address in self.fail_addresses:
            return FakeResponse(error=True)
        return FakeResponse([self.memory.get(address + i, 0) for i in range(count)])

    async def write_register(
        self, address: int, value: int, *, device_id: int = 1
    ) -> FakeResponse:
        """Write a single register."""
        return self._write(address, [value])

    async def write_registers(
        self, address: int, values: list[int], *, device_id: int = 1
    ) -> FakeResponse:
        """Write several consecutive registers."""
        return self._write(address, list(values))

    def _write(self, address: int, values: list[int]) -> FakeResponse:
        if self.fail_writes:
            return FakeResponse(error=True)
        self.writes.append((address, values))
        for offset, word in enumerate(values):
            self.memory[address + offset] = word
        return FakeResponse()

    def reads_of(self, address: int) -> int:
        """Return how many times a register was read."""
        return sum(1 for read in self.reads if read[0] == address)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests in this package."""
    yield


@pytest.fixture(autouse=True)
def no_message_wait() -> Generator[None]:
    """Remove the delay between two Modbus requests to speed up the tests."""
    with patch("custom_components.eprowallbox.coordinator.MESSAGE_WAIT", 0):
        yield


@pytest.fixture(autouse=True)
def mock_frontend(hass: Any) -> Generator[MagicMock]:
    """Do not set up the real frontend / http components.

    La dépendance `frontend` et `http` de l'intégration est considérée comme
    déjà chargée ; l'enregistrement de la carte est simulé.
    """
    hass.config.components.update({"frontend", "http"})
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    with patch(
        "custom_components.eprowallbox.add_extra_js_url"
    ) as add_extra_js_url:
        yield add_extra_js_url


@pytest.fixture
def mock_modbus() -> Generator[FakeModbusClient]:
    """Replace AsyncModbusTcpClient by a fake wallbox everywhere it is used."""
    client = FakeModbusClient()
    with (
        patch(
            "custom_components.eprowallbox.coordinator.AsyncModbusTcpClient",
            return_value=client,
        ),
        patch(
            "custom_components.eprowallbox.config_flow.AsyncModbusTcpClient",
            return_value=client,
        ),
    ):
        yield client


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry to prevent full integration setup during config flow tests."""
    with patch(
        "custom_components.eprowallbox.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a mock config entry for tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="eProWallbox",
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 502},
    )


@pytest.fixture
async def init_integration(
    hass: Any,
    mock_config_entry: MockConfigEntry,
    mock_modbus: FakeModbusClient,
) -> MockConfigEntry:
    """Set up the integration with the fake wallbox."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
