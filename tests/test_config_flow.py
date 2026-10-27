"""Tests of the config flow of the GCE IPX800 V4 integration."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.ipx800v4 import CONFIG_SCHEMA
from custom_components.ipx800v4.const import DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from .conftest import ENTRY_DATA, NAME, YAML_CONFIG


async def test_user_yaml_only(hass: HomeAssistant) -> None:
    """Test the user step explains the configuration is done in YAML."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "yaml_only"


async def test_import(hass: HomeAssistant, mock_clients: MagicMock) -> None:
    """Test the import of the YAML configuration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data=ENTRY_DATA
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == ENTRY_DATA
    assert result["result"].unique_id == f"{DOMAIN}, {NAME}"


async def test_import_updates_not_loaded_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the YAML import updates an entry which isn't loaded, without setup."""
    mock_config_entry.add_to_hass(hass)
    data = ENTRY_DATA | {CONF_SCAN_INTERVAL: 60}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data=data
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data == data
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_options_entry_not_loaded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
) -> None:
    """Test the options of an entry which isn't loaded, then set up with them."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    # Prefilled with the interval of the YAML configuration
    schema = result["data_schema"].schema
    (key,) = schema
    assert key.default() == ENTRY_DATA[CONF_SCAN_INTERVAL]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_SCAN_INTERVAL: 60}
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_options_reload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
) -> None:
    """Test new options reload the entry with the new interval."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.state is ConfigEntryState.LOADED
    data = mock_config_entry.runtime_data
    assert data.coordinator.update_interval.total_seconds() == 60
    assert data.system_coordinator.update_interval.total_seconds() == 60
    assert mock_clients.global_get.await_count == 2


async def test_options_scan_interval_minimum(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test a scan interval of 0, a polling without pause, is refused."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 0}
        )
    assert mock_config_entry.options == {}


def test_yaml_scan_interval_minimum() -> None:
    """Test the YAML configuration refuses a scan interval of 0."""
    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA({DOMAIN: [YAML_CONFIG | {CONF_SCAN_INTERVAL: 0}]})
