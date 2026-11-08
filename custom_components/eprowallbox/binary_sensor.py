"""Binary sensor platform for eProWallbox."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EprowallboxConfigEntry
from .const import DOMAIN
from .coordinator import TemplateCoordinator

PARALLEL_UPDATES = 0

# Capteurs binaires Modbus : bit 0 du registre (0 = off, 1 = on).
# La clé correspond à la clé attendue dans `coordinator.data`.
BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="load_unbalance_limiting",  # registre 40106
        name="Load Unbalance Limiting",
    ),
    BinarySensorEntityDescription(
        key="dpm_limiting",  # registre 40107
        name="DPM Limiting",
    ),
    BinarySensorEntityDescription(
        key="temperature_derating",  # registre 40108, actif au-dessus de 85 °C
        name="Temperature Derating",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    BinarySensorEntityDescription(
        key="dpm_enabled",  # registre 40400
        name="DPM Enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="mid_meter_enabled",  # registre 40401
        name="MID Meter Enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="load_unbalance_enabled",  # registre 40402
        name="Load Unbalance Enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="watchdog_enabled",  # registre 40412
        name="Watchdog Enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EprowallboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator = entry.runtime_data.coordinator

    entities: list[BinarySensorEntity] = [EprowallboxStatusSensor(coordinator, entry)]
    entities.extend(
        EprowallboxBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )
    async_add_entities(entities)


def _device_info(entry: EprowallboxConfigEntry) -> DeviceInfo:
    """Return the device info shared by all eProWallbox entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="eProWallbox",
    )


class EprowallboxStatusSensor(
    CoordinatorEntity[TemplateCoordinator], BinarySensorEntity
):
    """Binary sensor indicating service connectivity."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: TemplateCoordinator,
        entry: EprowallboxConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_name = "Status"
        self._attr_device_info = _device_info(entry)

    @property
    def available(self) -> bool:
        """Stay available so that a lost connection is shown as "off"."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True if the service is reachable."""
        return self.coordinator.last_update_success


class EprowallboxBinarySensor(
    CoordinatorEntity[TemplateCoordinator], BinarySensorEntity
):
    """Binary sensor backed by bit 0 of a Modbus register."""

    entity_description: BinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TemplateCoordinator,
        entry: EprowallboxConfigEntry,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool | None:
        """Return True if bit 0 of the register is set."""
        if self.coordinator.data is None:
            return None

        value = self.coordinator.data.get(self.entity_description.key)
        if value is None:
            return None

        try:
            return bool(int(value) & 1)
        except (TypeError, ValueError):
            return None
