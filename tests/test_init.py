"""Tests of the setup of the GCE IPX800 V4 integration."""

from copy import deepcopy
from unittest.mock import MagicMock

from pypx800 import Ipx800CannotConnectError, Ipx800InvalidAuthError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.ipx800v4.const import DOMAIN
from custom_components.ipx800v4.coordinator import PUSH_ENTRIES
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.setup import async_setup_component

from .conftest import ENTRY_DATA, HOST, MAC, NAME, YAML_CONFIG


async def test_setup_and_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
) -> None:
    """Test the setup and unload of an entry."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    data = mock_config_entry.runtime_data
    assert data.coordinator.data["R1"] == 1
    assert data.push_config is not None
    assert hass.data[PUSH_ENTRIES][mock_config_entry.entry_id] is data

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    assert hass.data[PUSH_ENTRIES] == {}
    # Home Assistant shut down the coordinators with the entry
    assert data.coordinator._shutdown_requested
    assert data.system_coordinator._shutdown_requested


async def test_setup_cannot_connect(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
) -> None:
    """Test the setup is retried when the IPX800 is unreachable."""
    mock_clients.global_get.side_effect = Ipx800CannotConnectError
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_invalid_auth(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
) -> None:
    """Test rejected credentials raise a repair issue, the entry has no reauth."""
    mock_clients.global_get.side_effect = Ipx800InvalidAuthError
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    issue_id = f"invalid_auth_{mock_config_entry.entry_id}"
    issue = issue_registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "invalid_auth"
    assert issue.translation_placeholders == {"name": NAME}

    await hass.config_entries.async_remove(mock_config_entry.entry_id)
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_invalid_auth_issue_deleted_after_reload(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
) -> None:
    """Test the repair issue is deleted once a reloaded entry reads the IPX800."""
    mock_clients.global_get.side_effect = Ipx800InvalidAuthError
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    issue_id = f"invalid_auth_{mock_config_entry.entry_id}"
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None

    # The credentials are fixed in configuration.yaml, then the entry reloaded
    mock_clients.global_get.side_effect = None
    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_import_from_yaml(hass: HomeAssistant, mock_clients: MagicMock) -> None:
    """Test the YAML configuration creates the entry, and updates it."""
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: [YAML_CONFIG]})
    await hass.async_block_till_done()

    (entry,) = hass.config_entries.async_entries(DOMAIN)
    assert entry.title == NAME
    assert entry.unique_id == f"{DOMAIN}, {NAME}"
    assert entry.data == ENTRY_DATA
    assert entry.state is ConfigEntryState.LOADED
    assert mock_clients.global_get.await_count == 1

    # A YAML change replaces the data, removed keys included, and reloads
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "import"},
        data={
            key: value for key, value in ENTRY_DATA.items() if key != "push_password"
        },
    )
    await hass.async_block_till_done()
    assert result["reason"] == "already_configured"
    assert "push_password" not in entry.data
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.push_config is None
    assert mock_clients.global_get.await_count == 2


async def test_controller_mac_address(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
) -> None:
    """Test the MAC address read in the diagnostics is set on the controller."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    controller = device_registry.async_get(
        mock_config_entry.runtime_data.coordinator.controller_device_id
    )
    assert controller.identifiers == {(DOMAIN, HOST)}
    assert controller.connections == {(dr.CONNECTION_NETWORK_MAC, MAC)}


async def test_same_device_names_on_two_ipx800(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    mock_clients: MagicMock,
    mock_command_client: MagicMock,
) -> None:
    """Test devices having the same name on two IPX800 are distinct devices."""
    entries = []
    for name, host in ((NAME, HOST), ("Garage IPX800", "192.168.1.241")):
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=name,
            unique_id=f"{DOMAIN}, {name}",
            data=deepcopy(ENTRY_DATA) | {"name": name, "host": host},
        )
        entry.add_to_hass(hass)
        entries.append(entry)
        mock_clients.host = mock_command_client.host = host
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    boilers = [
        device_registry.async_get(entity_registry.async_get(entity_id).device_id)
        for entity_id in ("switch.boiler", "switch.boiler_2")
    ]
    assert boilers[0].id != boilers[1].id
    assert [device.config_entry_id for device in boilers] == [
        entry.entry_id for entry in entries
    ]
    assert [device.via_device_id for device in boilers] == [
        entry.runtime_data.coordinator.controller_device_id for entry in entries
    ]


@pytest.mark.parametrize(("with_entities", "removed"), [(True, False), (False, True)])
async def test_remove_device(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
    with_entities: bool,
    removed: bool,
) -> None:
    """Test only a device left without entities can be removed."""
    assert await async_setup_component(hass, "config", {})
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    if with_entities:
        device_id = entity_registry.async_get("switch.boiler").device_id
    else:
        device_id = device_registry.async_get_or_create(
            config_entry_id=mock_config_entry.entry_id,
            identifiers={(DOMAIN, "removed_from_yaml")},
        ).id

    client = await hass_ws_client(hass)
    response = await client.remove_device(device_id)
    assert response["success"] is removed
    assert (device_registry.async_get(device_id) is None) is removed


async def test_upgrade_keeps_entities_of_a_previous_version(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_clients: MagicMock,
) -> None:
    """Test an upgrade from the legacy names keeps the entities and their names.

    The previous versions registered the entities with has_entity_name=False
    and the user may have renamed their devices.
    """
    mock_config_entry.add_to_hass(hass)
    boiler = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, "boiler")},
        name="Boiler",
    )
    device_registry.async_update_device(boiler.id, name_by_user="Chaudière")
    living_room = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, "living_room")},
        name="Living room",
    )
    for domain, object_id, unique_id, name, device_id in (
        ("switch", "boiler", "switch_boiler", "Boiler", boiler.id),
        (
            "sensor",
            "living_room_temperature",
            "sensor_living_room_temperature",
            "Living room Temperature",
            living_room.id,
        ),
    ):
        entity_registry.async_get_or_create(
            domain,
            DOMAIN,
            f"{DOMAIN}_{HOST}_{unique_id}",
            suggested_object_id=object_id,
            config_entry=mock_config_entry,
            device_id=device_id,
            has_entity_name=False,
            original_name=name,
        )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entities = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    assert not [entity for entity in entities if entity.entity_id.endswith("_2")]
    boiler_entity = entity_registry.async_get("switch.boiler")
    assert boiler_entity.device_id == boiler.id
    assert boiler_entity.has_entity_name
    # The main entity takes the name the user gave to its device
    assert hass.states.get("switch.boiler").attributes["friendly_name"] == "Chaudière"
    assert device_registry.async_get(boiler.id).name_by_user == "Chaudière"
    temperature = entity_registry.async_get("sensor.living_room_temperature")
    assert temperature.device_id == living_room.id
    assert (
        hass.states.get("sensor.living_room_temperature").attributes["friendly_name"]
        == "Living room Temperature"
    )
