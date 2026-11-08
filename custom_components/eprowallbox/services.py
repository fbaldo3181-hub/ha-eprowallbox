"""Service handlers for the eProWallbox integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import CannotConnectError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_QUERY = "query"

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("query"): cv.string,
    }
)


async def _async_handle_query(call: ServiceCall) -> ServiceResponse:
    """Handle the query service call for eProWallbox."""
    query: str = call.data["query"]

    entries = call.hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(
            f"No {DOMAIN} integration configured"
        )

    coordinator = entries[0].runtime_data.coordinator

    # TODO: Implement with actual coordinator/client data
    try:
        data = coordinator.data or {}
    except CannotConnectError as err:
        raise HomeAssistantError(f"Service call failed: {err}") from err

    result: dict[str, Any] = {"query": query, "results": data}
    return result


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register integration service actions for eProWallbox."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_QUERY,
        _async_handle_query,
        schema=SERVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
