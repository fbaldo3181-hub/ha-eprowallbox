"""Sensor platform for eProWallbox."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EprowallboxConfigEntry
from .const import DOMAIN
from .coordinator import TemplateCoordinator

PARALLEL_UPDATES = 0

PHASES = ("l1", "l2", "l3")


@dataclass(frozen=True, kw_only=True)
class EprowallboxSensorDescription(SensorEntityDescription):
    """Sensor description with the Modbus scale / offset conversion.

    La valeur finale est : valeur_brute * scale + offset (même logique que
    les options `scale` et `offset` de l'intégration Modbus).
    """

    scale: float = 1
    offset: float = 0


def _per_phase(
    prefix: str,
    label: str,
    **kwargs,
) -> tuple[EprowallboxSensorDescription, ...]:
    """Build one description per phase (L1, L2, L3)."""
    return tuple(
        EprowallboxSensorDescription(
            key=f"{prefix}_{phase}",
            name=f"{label} {phase.upper()}",
            **kwargs,
        )
        for phase in PHASES
    )


SENSOR_DESCRIPTIONS: tuple[EprowallboxSensorDescription, ...] = (
    # ---- Identification (lecture rare) ----
    EprowallboxSensorDescription(
        key="serial_number",
        name="Serial Number",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EprowallboxSensorDescription(
        key="firmware_version",
        name="Firmware Version",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EprowallboxSensorDescription(
        key="modbus_map_version",
        name="Modbus Map Version",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EprowallboxSensorDescription(
        key="device_type",  # 0 = AC monophasé, 1 = AC triphasé
        name="Device Type",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EprowallboxSensorDescription(
        key="hw_current_limit",  # position du sélecteur rotatif
        name="HW Current Limit",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        suggested_display_precision=0,
        scale=0.001,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # ---- États ----
    EprowallboxSensorDescription(
        key="actual_error",
        name="Actual Error",
    ),
    EprowallboxSensorDescription(
        key="general_status",  # 0 = A1 ... 9 = F (IEC 61851)
        name="General Status",
    ),
    EprowallboxSensorDescription(
        key="ocpp_status",  # 0 = Available ... 8 = Faulted
        name="OCPP Status",
    ),
    EprowallboxSensorDescription(
        key="user_current_limit",  # limite fixée via l'app
        name="User Current Limit",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        suggested_display_precision=0,
        scale=0.001,
    ),
    # ---- Paramètres lus en retour ----
    EprowallboxSensorDescription(
        key="current_limit",  # consigne EMS (40407)
        name="Current Limit",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        suggested_display_precision=0,
        scale=0.001,
    ),
    EprowallboxSensorDescription(
        key="fallback_current",  # courant de repli si perte EMS
        name="Fallback Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        suggested_display_precision=0,
        scale=0.001,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EprowallboxSensorDescription(
        key="load_unbalance_current",
        name="Load Unbalance Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        suggested_display_precision=0,
        scale=0.001,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EprowallboxSensorDescription(
        key="watchdog_timer",
        name="Watchdog Timer",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EprowallboxSensorDescription(
        key="meter_used",  # 0 = compteur externe, 1 = interne
        name="Meter Used",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # ---- Session / température ----
    EprowallboxSensorDescription(
        key="charge_time",
        name="Charge Time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    EprowallboxSensorDescription(
        key="temperature",  # registre en kelvin -> °C
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        offset=-273.15,
    ),
    # ---- Tensions (mV -> V) ----
    *_per_phase(
        "voltage",
        "Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.001,
    ),
    # ---- THD tension ----
    *_per_phase(
        "thd_voltage",
        "THD Voltage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # ---- Courants ----
    *_per_phase(
        "current",
        "Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    # ---- THD courant ----
    *_per_phase(
        "thd_current",
        "THD Current",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # ---- Puissances actives ----
    *_per_phase(
        "active_power",
        "Active Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    # ---- Puissances réactives ----
    *_per_phase(
        "reactive_power",
        "Reactive Power",
        native_unit_of_measurement="var",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    # ---- Puissances apparentes ----
    *_per_phase(
        "apparent_power",
        "Apparent Power",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    # ---- Énergies actives ----
    *_per_phase(
        "active_energy",
        "Active Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    # ---- Énergies réactives ----
    *_per_phase(
        "reactive_energy",
        "Reactive Energy",
        native_unit_of_measurement="varh",
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EprowallboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator = entry.runtime_data.coordinator

    async_add_entities(
        EprowallboxSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class EprowallboxSensor(CoordinatorEntity[TemplateCoordinator], SensorEntity):
    """Representation of an eProWallbox sensor."""

    entity_description: EprowallboxSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TemplateCoordinator,
        entry: ConfigEntry,
        description: EprowallboxSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="eProWallbox",
        )

    @property
    def native_value(self) -> str | int | float | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None

        value = self.coordinator.data.get(self.entity_description.key)
        if value is None:
            return None

        scale = self.entity_description.scale
        offset = self.entity_description.offset
        if scale == 1 and offset == 0:
            return value

        try:
            return float(value) * scale + offset
        except (TypeError, ValueError):
            return None
