"""DataUpdateCoordinator for eProWallbox (Modbus TCP)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import logging
import math
import struct
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Paramètres de la connexion (repris de la config modbus du YAML)
SLAVE_ID = 1
TIMEOUT = 5
MESSAGE_WAIT = 0.03  # message_wait_milliseconds: 30

# Le coordinator "tourne" à la période du registre le plus rapide ; chaque
# registre n'est relu que lorsque son propre scan_interval est écoulé.
BASE_UPDATE_INTERVAL = 5

_ERRORS = (ModbusException, OSError, TimeoutError)

_WORDS = {"uint16": 1, "uint32": 2, "float32": 2}


@dataclass(frozen=True)
class Register:
    """Description d'un registre (ou groupe de registres) Modbus holding."""

    key: str
    address: int
    data_type: str = "uint16"  # uint16 | uint32 | float32 | string
    interval: int = 300  # scan_interval en secondes
    count: int = 0  # nombre de registres, obligatoire pour "string"

    @property
    def words(self) -> int:
        """Nombre de registres 16 bits à lire."""
        return self.count or _WORDS[self.data_type]


def _phases(
    prefix: str, start: int, data_type: str, interval: int
) -> tuple[Register, ...]:
    """Trois registres consécutifs (L1, L2, L3), espacés de 2 registres."""
    return tuple(
        Register(f"{prefix}_l{n}", start + 2 * (n - 1), data_type, interval)
        for n in (1, 2, 3)
    )


REGISTERS: tuple[Register, ...] = (
    # ---- Identification (lecture rare) ----
    Register("serial_number", 40000, "string", 3600, count=8),
    Register("firmware_version", 40008, "string", 3600, count=4),
    Register("modbus_map_version", 40012, "string", 3600, count=4),
    Register("device_type", 40017, "uint16", 3600),
    Register("hw_current_limit", 40018, "uint32", 300),
    # ---- États ----
    Register("actual_error", 40100, "uint16", 10),
    Register("general_status", 40101, "uint16", 5),
    Register("ocpp_status", 40102, "uint16", 5),
    Register("user_current_limit", 40103, "uint32", 30),
    # ---- Binary sensors (bit 0) ----
    Register("load_unbalance_limiting", 40106, "uint16", 30),
    Register("dpm_limiting", 40107, "uint16", 30),
    Register("temperature_derating", 40108, "uint16", 30),
    Register("dpm_enabled", 40400, "uint16", 300),
    Register("mid_meter_enabled", 40401, "uint16", 300),
    Register("load_unbalance_enabled", 40402, "uint16", 300),
    Register("watchdog_enabled", 40412, "uint16", 300),
    # ---- Paramètres lus en retour ----
    Register("load_unbalance_current", 40403, "uint32", 300),
    Register("charging_enabled", 40406, "uint16", 15),  # switch
    Register("current_limit", 40407, "uint32", 15),
    Register("fallback_current", 40409, "uint32", 300),
    Register("meter_used", 40411, "uint16", 300),
    Register("watchdog_timer", 40413, "uint16", 300),
    # ---- Session / température ----
    Register("charge_time", 40600, "uint32", 30),
    Register("temperature", 40602, "float32", 30),
    # ---- Mesures par phase ----
    *_phases("voltage", 40604, "float32", 10),
    *_phases("thd_voltage", 40610, "float32", 60),
    *_phases("current", 40620, "float32", 10),
    *_phases("thd_current", 40626, "float32", 60),
    *_phases("active_power", 40636, "float32", 10),
    *_phases("reactive_power", 40642, "float32", 30),
    *_phases("apparent_power", 40648, "float32", 30),
    *_phases("active_energy", 40658, "float32", 30),
    *_phases("reactive_energy", 40664, "float32", 60),
)


def _decode(register: Register, words: list[int]) -> Any:
    """Décoder les registres bruts (big-endian, sans scale ni offset)."""
    if register.data_type == "string":
        raw = struct.pack(f">{len(words)}H", *words)
        return raw.decode("ascii", errors="ignore").strip("\x00 ")
    if register.data_type == "uint16":
        return words[0]
    if register.data_type == "uint32":
        return (words[0] << 16) | words[1]
    if register.data_type == "float32":
        value = struct.unpack(">f", struct.pack(">HH", words[0], words[1]))[0]
        return None if math.isnan(value) else value
    raise ValueError(f"Unsupported data type: {register.data_type}")


class TemplateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage Modbus TCP communication with the wallbox."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=BASE_UPDATE_INTERVAL),
        )
        self.client = AsyncModbusTcpClient(
            entry.data[CONF_HOST],
            port=entry.data[CONF_PORT],
            timeout=TIMEOUT,
        )
        # pymodbus >= 3.10 : "device_id" ; versions précédentes : "slave"
        self._slave_kwarg = (
            "device_id"
            if "device_id" in inspect.signature(self.client.read_holding_registers).parameters
            else "slave"
        )
        self._lock = asyncio.Lock()
        self._values: dict[str, Any] = {}
        self._next_due: dict[str, float] = {}
        self._failed_keys: set[str] = set()

    async def _async_connect(self) -> None:
        """Ouvrir la connexion TCP si nécessaire (lock déjà pris)."""
        if self.client.connected:
            return
        try:
            connected = await self.client.connect()
        except _ERRORS as err:
            raise UpdateFailed(f"Cannot connect to the wallbox: {err}") from err
        if not connected:
            raise UpdateFailed("Cannot connect to the wallbox")

    async def _async_update_data(self) -> dict[str, Any]:
        """Lire les registres dont le scan_interval est écoulé."""
        async with self._lock:
            await self._async_connect()

            now = time.monotonic()
            due = [r for r in REGISTERS if self._next_due.get(r.key, 0) <= now]
            errors = 0
            comm_errors = 0

            for register in due:
                try:
                    response = await self.client.read_holding_registers(
                        register.address,
                        count=register.words,
                        **{self._slave_kwarg: SLAVE_ID},
                    )
                except _ERRORS as err:
                    response = None
                    comm_errors += 1
                    _LOGGER.debug("Read error on %s: %s", register.key, err)

                if response is None or response.isError():
                    errors += 1
                    if register.key not in self._failed_keys:
                        self._failed_keys.add(register.key)
                        _LOGGER.warning(
                            "Cannot read %s (register %s)",
                            register.key,
                            register.address,
                        )
                else:
                    self._failed_keys.discard(register.key)
                    self._values[register.key] = _decode(register, response.registers)

                self._next_due[register.key] = time.monotonic() + register.interval
                await asyncio.sleep(MESSAGE_WAIT)

            # Échec de la mise à jour seulement si la borne ne répond plus
            # (toutes les lectures dues ont levé une erreur de communication)
            # ou si rien n'a jamais pu être lu. Un registre refusé alors que la
            # borne répond (exception Modbus) garde simplement sa dernière valeur.
            if due and errors == len(due) and (
                comm_errors == len(due) or not self._values
            ):
                raise UpdateFailed("No register could be read from the wallbox")

        return dict(self._values)

    async def async_write_register(self, address: int, value: int) -> None:
        """Écrire un registre holding (utilisé par la plateforme switch)."""
        await self.async_write_registers(address, [value])

    async def async_write_registers(self, address: int, values: list[int]) -> None:
        """Écrire un ou plusieurs registres holding consécutifs."""
        async with self._lock:
            try:
                await self._async_connect()
                if len(values) == 1:
                    response = await self.client.write_register(
                        address, values[0], **{self._slave_kwarg: SLAVE_ID}
                    )
                else:
                    response = await self.client.write_registers(
                        address, values, **{self._slave_kwarg: SLAVE_ID}
                    )
            except (UpdateFailed, *_ERRORS) as err:
                raise HomeAssistantError(
                    f"Cannot write register {address}: {err}"
                ) from err
            if response.isError():
                raise HomeAssistantError(f"Write to register {address} refused")

        # Forcer la relecture des registres écrits au prochain rafraîchissement
        written = range(address, address + len(values))
        for register in REGISTERS:
            if register.address in written:
                self._next_due[register.key] = 0

    async def async_shutdown(self) -> None:
        """Fermer la connexion Modbus."""
        await super().async_shutdown()
        result = self.client.close()
        if inspect.isawaitable(result):
            await result
