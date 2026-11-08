"""The eProWallbox integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, FRONTEND_SCRIPT_URL, FRONTEND_VERSION
from .coordinator import TemplateCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class EprowallboxData:
    """Data for the eProWallbox integration."""

    coordinator: TemplateCoordinator


type EprowallboxConfigEntry = ConfigEntry[EprowallboxData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve the Lovelace card and load it on every dashboard."""
    card = Path(__file__).parent / "frontend" / f"{DOMAIN}-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_SCRIPT_URL, str(card), cache_headers=True)]
    )
    add_extra_js_url(hass, f"{FRONTEND_SCRIPT_URL}?v={FRONTEND_VERSION}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EprowallboxConfigEntry) -> bool:
    """Set up eProWallbox from a config entry."""
    coordinator = TemplateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = EprowallboxData(coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EprowallboxConfigEntry) -> bool:
    """Unload a config entry (the coordinator closes the Modbus connection)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
