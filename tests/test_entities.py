"""Tests of the entities of the GCE IPX800 V4 integration."""

from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .conftest import HOST


@pytest.mark.parametrize(
    "platform",
    [
        Platform.BINARY_SENSOR,
        Platform.CLIMATE,
        Platform.COVER,
        Platform.LIGHT,
        Platform.NUMBER,
        Platform.SENSOR,
        Platform.SWITCH,
    ],
)
async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
    platform: Platform,
) -> None:
    """Test the entities and their states."""
    with patch("custom_components.ipx800v4.PLATFORMS", [platform]):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_unique_ids_are_stable(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
) -> None:
    """Test the unique IDs keep the format of the previous versions."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    for entity_id, unique_id in (
        ("switch.boiler", f"ipx800v4_{HOST}_switch_boiler"),
        (
            "sensor.living_room_temperature",
            f"ipx800v4_{HOST}_sensor_living_room_temperature",
        ),
        (
            "sensor.living_room_luminance",
            f"ipx800v4_{HOST}_sensor_living_room_luminance",
        ),
        ("sensor.ipx800_load", f"ipx800v4_{HOST}_diagnostic_load"),
    ):
        assert entity_registry.async_get(entity_id).unique_id == unique_id


async def test_command_error_is_translated(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
    mock_command_client: MagicMock,
) -> None:
    """Test a refused command raises a translated error."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.boiler"},
        blocking=True,
    )
    mock_command_client.request_api.assert_awaited_with({"ClearR": 1})

    mock_command_client.request_api.side_effect = TimeoutError
    with (
        patch("custom_components.ipx800v4.commands.asyncio.sleep"),
        pytest.raises(HomeAssistantError) as raised,
    ):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "switch.boiler"},
            blocking=True,
        )
    assert raised.value.translation_key == "command_failed"
    assert str(raised.value).startswith("Cannot confirm turn off for switch.boiler: ")


@pytest.mark.parametrize(("value", "sent"), [(12.0, 12), (12.6, 13)])
async def test_counter_number_sends_an_integer(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
    mock_command_client: MagicMock,
    value: float,
    sent: int,
) -> None:
    """Test a counter number sends an integer, number.set_value gives a float."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.pulse_counter", ATTR_VALUE: value},
        blocking=True,
    )
    mock_command_client.request_api.assert_awaited_with({"SetC02": sent})
    (params,) = mock_command_client.request_api.await_args.args
    assert type(params["SetC02"]) is int
