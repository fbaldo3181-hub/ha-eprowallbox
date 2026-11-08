"""Tests for eProWallbox config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eprowallbox.config_flow import (
    CannotConnect,
    _async_validate_connection,
)
from custom_components.eprowallbox.const import DOMAIN

from .conftest import FakeModbusClient

VALIDATE = "custom_components.eprowallbox.config_flow._async_validate_connection"


async def test_form(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """Test the user config flow form — successful setup."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}

    with patch(VALIDATE, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100", CONF_PORT: 502},
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "eProWallbox"
    assert result["data"] == {CONF_HOST: "192.168.1.100", CONF_PORT: 502}
    assert result["result"].unique_id == "192.168.1.100:502"
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_with_real_validation(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_modbus: FakeModbusClient,
) -> None:
    """Test the full flow, including the Modbus connection test."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100", CONF_PORT: 502},
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    # Registre du numéro de série lu pour tester la connexion
    assert mock_modbus.reads == [(40000, 8, 1)]
    assert mock_modbus.closed


async def test_form_default_port(hass: HomeAssistant) -> None:
    """The port field defaults to the standard Modbus TCP port."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    schema = result["data_schema"].schema
    port_key = next(key for key in schema if key == CONF_PORT)
    assert port_key.default() == 502


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (CannotConnect, "cannot_connect"),
        (RuntimeError, "unknown"),
    ],
)
async def test_form_errors(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    exception: type[Exception],
    error: str,
) -> None:
    """Errors are shown on the form and the flow can then succeed."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(VALIDATE, side_effect=exception):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100", CONF_PORT: 502},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": error}

    # La saisie suivante, valide, termine le flux
    with patch(VALIDATE, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100", CONF_PORT: 502},
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_form_duplicate_abort(hass: HomeAssistant) -> None:
    """Test the config flow aborts when the same host:port is already configured."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.100:502",
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 502},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM

    with patch(VALIDATE, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100", CONF_PORT: 502},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant) -> None:
    """Test the options flow validates, updates entry.data, and reloads."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 502},
    )
    entry.add_to_hass(hass)

    # Mock setup/unload so reload succeeds
    with (
        patch(
            "custom_components.eprowallbox.async_setup_entry",
            return_value=True,
        ),
        patch(
            "custom_components.eprowallbox.async_unload_entry",
            return_value=True,
        ),
        patch(VALIDATE, return_value=None),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: "192.168.1.200", CONF_PORT: 1502},
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_HOST] == "192.168.1.200"
    assert entry.data[CONF_PORT] == 1502


async def test_options_flow_error(hass: HomeAssistant) -> None:
    """Test the options flow shows errors on validation failure without reloading."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 502},
    )
    entry.add_to_hass(hass)

    with patch(VALIDATE, side_effect=CannotConnect):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: "bad-host", CONF_PORT: 502},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    # Original data unchanged
    assert entry.data[CONF_HOST] == "192.168.1.100"


# ---------------------------------------------------------------------------
# _async_validate_connection
# ---------------------------------------------------------------------------


async def test_validate_connection_success(
    hass: HomeAssistant, mock_modbus: FakeModbusClient
) -> None:
    """A wallbox answering on the test register is accepted."""
    await _async_validate_connection(hass, {CONF_HOST: "192.168.1.100", CONF_PORT: 502})

    assert mock_modbus.reads == [(40000, 8, 1)]
    assert mock_modbus.closed


async def test_validate_connection_refused(
    hass: HomeAssistant, mock_modbus: FakeModbusClient
) -> None:
    """A connection that cannot be opened raises CannotConnect."""
    mock_modbus.connect_ok = False

    with pytest.raises(CannotConnect):
        await _async_validate_connection(
            hass, {CONF_HOST: "192.168.1.100", CONF_PORT: 502}
        )

    assert mock_modbus.closed


async def test_validate_connection_read_refused(
    hass: HomeAssistant, mock_modbus: FakeModbusClient
) -> None:
    """A device refusing the test register raises CannotConnect."""
    mock_modbus.fail_all_reads = True

    with pytest.raises(CannotConnect):
        await _async_validate_connection(
            hass, {CONF_HOST: "192.168.1.100", CONF_PORT: 502}
        )

    assert mock_modbus.closed


@pytest.mark.parametrize("exception", [OSError, TimeoutError])
async def test_validate_connection_network_error(
    hass: HomeAssistant,
    mock_modbus: FakeModbusClient,
    exception: type[Exception],
) -> None:
    """Network errors are reported as CannotConnect."""
    with (
        patch.object(mock_modbus, "connect", side_effect=exception),
        pytest.raises(CannotConnect),
    ):
        await _async_validate_connection(
            hass, {CONF_HOST: "192.168.1.100", CONF_PORT: 502}
        )

    assert mock_modbus.closed
