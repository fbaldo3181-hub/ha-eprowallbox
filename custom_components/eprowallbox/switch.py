"""Switch platform for eProWallbox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EprowallboxConfigEntry
from .const import DOMAIN
from .coordinator import TemplateCoordinator

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class EprowallboxSwitchDescription(SwitchEntityDescription):
    """Switch description backed by a Modbus holding register."""

    address: int
    command_on: int = 1
    command_off: int = 0


SWITCH_DESCRIPTIONS: tuple[EprowallboxSwitchDescription, ...] = (
    EprowallboxSwitchDescription(
        key="charging_enabled",  # ON_OFF_INPUT
        name="Charging Enabled",
        address=40406,
        command_on=1,
        command_off=0,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EprowallboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities."""
    coordinator = entry.runtime_data.coordinator

    async_add_entities(
        EprowallboxSwitch(coordinator, entry, description)
        for description in SWITCH_DESCRIPTIONS
    )


class EprowallboxSwitch(CoordinatorEntity[TemplateCoordinator], SwitchEntity):
    """Switch writing to a Modbus holding register."""

    entity_description: EprowallboxSwitchDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TemplateCoordinator,
        entry: EprowallboxConfigEntry,
        description: EprowallboxSwitchDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="eProWallbox",
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the register reads back the 'on' command value."""
        if self.coordinator.data is None:
            return None

        value = self.coordinator.data.get(self.entity_description.key)
        if value is None:
            return None

        try:
            return int(value) == self.entity_description.command_on
        except (TypeError, ValueError):
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_write(self.entity_description.command_on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_write(self.entity_description.command_off)

    async def _async_write(self, value: int) -> None:
        """Write the register, then refresh to verify the new state."""
        # À implémenter dans le coordinator : écriture d'un registre holding.
        await self.coordinator.async_write_register(
            self.entity_description.address, value
        )
        # Équivalent du bloc `verify` du YAML : relecture du registre.
        await self.coordinator.async_request_refresh()
