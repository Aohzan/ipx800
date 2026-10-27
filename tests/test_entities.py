"""Tests of the entities of the GCE IPX800 V4 integration."""

import json
from pathlib import Path
import re
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.ipx800v4.const import DOMAIN
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
from homeassistant.helpers.translation import async_get_translations

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
    assert raised.value.translation_key == "command_failed_turn_off"
    assert str(raised.value).startswith("Cannot confirm turn off for switch.boiler: ")

    # The operation is part of the translation, not an English placeholder
    translations = await async_get_translations(hass, "fr", "exceptions", [DOMAIN])
    message = translations[
        f"component.{DOMAIN}.exceptions.command_failed_turn_off.message"
    ].format(**raised.value.translation_placeholders)
    assert message.startswith(
        "Impossible de confirmer l\u2019extinction de switch.boiler"
    )


def test_command_operations_are_translated() -> None:
    """Test every operation of a command error has its translations."""
    component = Path(__file__).parent.parent / "custom_components" / DOMAIN
    operations = {
        match
        for path in component.glob("*.py")
        for match in re.findall(
            r'_command_error\(\s*"(\w+)"', path.read_text(encoding="utf-8")
        )
    }
    assert "set_value" in operations
    for path in (component / "strings.json", *component.glob("translations/*.json")):
        exceptions = json.loads(path.read_text(encoding="utf-8"))["exceptions"]
        for kind in ("command_auth_failed", "command_failed", "command_interrupted"):
            for operation in operations:
                assert f"{kind}_{operation}" in exceptions, (path.name, operation)


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
