"""Helpers for the eProWallbox integration."""

from __future__ import annotations

import inspect

from pymodbus import FramerType
from pymodbus.client import AsyncModbusTcpClient

from .const import FRAMER_RTU


def create_client(host: str, port: int, framer: str, timeout: float) -> AsyncModbusTcpClient:
    """Créer le client Modbus avec la bonne trame (RTU sur TCP ou Modbus TCP)."""
    return AsyncModbusTcpClient(
        host,
        port=port,
        framer=FramerType.RTU if framer == FRAMER_RTU else FramerType.SOCKET,
        timeout=timeout,
    )


def slave_kwarg(client: AsyncModbusTcpClient) -> str:
    """pymodbus >= 3.10 : "device_id" ; versions précédentes : "slave"."""
    return (
        "device_id"
        if "device_id" in inspect.signature(client.read_holding_registers).parameters
        else "slave"
    )
