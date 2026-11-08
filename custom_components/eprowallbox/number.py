"""Number platform for eProWallbox."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EprowallboxConfigEntry
from .const import DOMAIN
from .coordinator import TemplateCoordinator

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class EprowallboxNumberDescription(NumberEntityDescription):
    """Number description backed by a 32-bit Modbus holding register (mA)."""

    data_key: str  # clé lue dans coordinator.data
    address: int  # adresse du premier registre (uint32 = 2 registres)
    scale: float = 0.001  # mA -> A
    max_key: str | None = None  # clé de la valeur maximale (en mA), optionnelle


NUMBER_DESCRIPTIONS: tuple[EprowallboxNumberDescription, ...] = (
    EprowallboxNumberDescription(
        key="current_limit_setpoint",  # consigne EMS (40407)
        name="Current Limit Setpoint",
        data_key="current_limit",
        address=40407,
        max_key="hw_current_limit",  # position du sélecteur rotatif
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_min_value=6,
        native_max_value=32,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EprowallboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""
    coordinator = entry.runtime_data.coordinator

    async_add_entities(
        EprowallboxNumber(coordinator, entry, description)
        for description in NUMBER_DESCRIPTIONS
    )


class EprowallboxNumber(CoordinatorEntity[TemplateCoordinator], NumberEntity):
    """Number writing a 32-bit value (mA) to two Modbus holding registers."""

    entity_description: EprowallboxNumberDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TemplateCoordinator,
        entry: EprowallboxConfigEntry,
        description: EprowallboxNumberDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="eProWallbox",
        )

    @property
    def native_max_value(self) -> float:
        """Limit the maximum to the hardware limit (rotary selector)."""
        description = self.entity_description
        maximum = description.native_max_value
        if description.max_key and self.coordinator.data is not None:
            raw = self.coordinator.data.get(description.max_key)
            if raw:
                maximum = float(raw) * description.scale
        return max(maximum, description.native_min_value)

    @property
    def native_value(self) -> float | None:
        """Return the value read back from the wallbox."""
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self.entity_description.data_key)
        if raw is None:
            return None
        return round(float(raw) * self.entity_description.scale, 3)

    async def async_set_native_value(self, value: float) -> None:
        """Write the new value, then refresh to read it back."""
        description = self.entity_description
        raw = round(value / description.scale)  # A -> mA
        registers = [(raw >> 16) & 0xFFFF, raw & 0xFFFF]
        await self.coordinator.async_write_registers(description.address, registers)
        await self.coordinator.async_request_refresh()
