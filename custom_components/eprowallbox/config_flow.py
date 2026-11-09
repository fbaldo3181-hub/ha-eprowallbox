"""Config flow for eProWallbox integration."""

from __future__ import annotations

import inspect
import logging
from typing import Any

import voluptuous as vol
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_FRAMER, DEFAULT_FRAMER, DEFAULT_PORT, DOMAIN, FRAMERS
from .coordinator import SLAVE_ID, TIMEOUT
from .helpers import create_client, slave_kwarg

_LOGGER = logging.getLogger(__name__)

# Registre de test : numéro de série (40000, 8 registres), toujours lisible.
TEST_REGISTER = 40000
TEST_REGISTER_COUNT = 8

PORT_VALIDATOR = vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))

FRAMER_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=FRAMERS,
        translation_key="framer",
        mode=SelectSelectorMode.DROPDOWN,
    )
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): PORT_VALIDATOR,
        vol.Required(CONF_FRAMER, default=DEFAULT_FRAMER): FRAMER_SELECTOR,
    }
)


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


async def _async_validate_connection(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> None:
    """Validate that the wallbox answers (Modbus RTU over TCP or Modbus TCP).

    Raise CannotConnect on failure.
    """
    client = create_client(
        user_input[CONF_HOST],
        user_input[CONF_PORT],
        user_input.get(CONF_FRAMER, DEFAULT_FRAMER),
        TIMEOUT,
    )
    slave_kw = slave_kwarg(client)
    try:
        if not await client.connect():
            raise CannotConnect
        response = await client.read_holding_registers(
            TEST_REGISTER,
            count=TEST_REGISTER_COUNT,
            **{slave_kw: SLAVE_ID},
        )
        if response.isError():
            _LOGGER.debug("Test register read refused: %s", response)
            raise CannotConnect
    except (ModbusException, OSError, TimeoutError) as err:
        raise CannotConnect from err
    finally:
        result = client.close()
        if inspect.isawaitable(result):
            await result


class TemplateConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for eProWallbox."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlowHandler:
        """Create the options flow."""
        return OptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            )
            self._abort_if_unique_id_configured()

            try:
                await _async_validate_connection(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="eProWallbox",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )


class OptionsFlowHandler(OptionsFlow):
    """Handle options flow for eProWallbox."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options (host and port of the wallbox)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            merged = {**self.config_entry.data, **user_input}
            try:
                await _async_validate_connection(self.hass, merged)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=merged
                )
                await self.hass.config_entries.async_reload(
                    self.config_entry.entry_id
                )
                return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=self.config_entry.data.get(CONF_HOST, ""),
                    ): str,
                    vol.Required(
                        CONF_PORT,
                        default=self.config_entry.data.get(
                            CONF_PORT, DEFAULT_PORT
                        ),
                    ): PORT_VALIDATOR,
                    vol.Required(
                        CONF_FRAMER,
                        default=self.config_entry.data.get(
                            CONF_FRAMER, DEFAULT_FRAMER
                        ),
                    ): FRAMER_SELECTOR,
                }
            ),
            errors=errors,
        )
