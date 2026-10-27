"""Fixtures of the GCE IPX800 V4 tests."""

from collections.abc import Generator
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

from custom_components.ipx800v4 import CONFIG_SCHEMA
from custom_components.ipx800v4.const import DOMAIN

HOST = "192.168.1.240"
NAME = "IPX800"
MAC = "00:04:a3:00:00:01"

# A device of every supported type, as written in configuration.yaml
DEVICES: list[dict[str, Any]] = [
    {"name": "Boiler", "component": "switch", "type": "relay", "id": 1},
    {"name": "Garage light", "component": "light", "type": "relay", "id": 2},
    {
        "name": "Heater",
        "component": "climate",
        "type": "relay",
        "ids": [3, 4],
    },
    {"name": "Scenario", "component": "switch", "type": "virtualout", "id": 1},
    {
        "name": "Motion",
        "component": "binary_sensor",
        "type": "virtualout",
        "id": 2,
        "device_class": "motion",
    },
    {"name": "Virtual input", "component": "switch", "type": "virtualin", "id": 1},
    {
        "name": "Doorbell",
        "component": "binary_sensor",
        "type": "digitalin",
        "id": 1,
        "invert_value": True,
        "icon": "mdi:bell",
    },
    {
        "name": "Tank level",
        "component": "sensor",
        "type": "analogin",
        "id": 1,
        "unit_of_measurement": "%",
    },
    {"name": "Setpoint", "component": "number", "type": "virtualanalogin", "id": 1},
    {
        "name": "Virtual value",
        "component": "sensor",
        "type": "virtualanalogin",
        "id": 2,
    },
    {"name": "Pulses", "component": "sensor", "type": "counter", "id": 1},
    {"name": "Pulse counter", "component": "number", "type": "counter", "id": 2},
    {"name": "Living room", "component": "sensor", "type": "xthl", "id": 1},
    {"name": "Outdoor sensor", "component": "sensor", "type": "xeno", "id": 121},
    {"name": "Plug", "component": "switch", "type": "xeno", "id": 1},
    {"name": "Dining room", "component": "light", "type": "xdimmer", "id": 1},
    {"name": "Kitchen spots", "component": "light", "type": "xpwm", "id": 1},
    {
        "name": "Stairs strip",
        "component": "light",
        "type": "xpwm_rgb",
        "ids": [2, 3, 4],
    },
    {
        "name": "Living room strip",
        "component": "light",
        "type": "xpwm_rgbw",
        "ids": [5, 6, 7, 8],
    },
    {
        "name": "Bedroom shutter",
        "component": "cover",
        "type": "x4vr",
        "ext_id": 1,
        "id": 1,
    },
    {
        "name": "Terrace blind",
        "component": "cover",
        "type": "x4vr_bso",
        "ext_id": 1,
        "id": 2,
    },
    {"name": "Bathroom", "component": "climate", "type": "x4fp", "ext_id": 1, "id": 1},
]

YAML_CONFIG: dict[str, Any] = {
    "name": NAME,
    "host": HOST,
    "api_key": "apikey",
    "username": "admin",
    "password": "secret",
    "push_password": "push-secret",
    "scan_interval": 30,
    "devices": DEVICES,
}

# Entry data imported from YAML, with the schema defaults
ENTRY_DATA: dict[str, Any] = CONFIG_SCHEMA({DOMAIN: [YAML_CONFIG]})[DOMAIN][0]

# Values returned by IPX800.global_get
IPX_DATA: dict[str, Any] = {
    "R1": 1,
    "R2": 0,
    "R3": 0,
    "R4": 1,
    "VO1": 1,
    "VO2": 0,
    "VI1": 0,
    "D1": 0,
    "A1": 42.5,
    "VA1": 21,
    "VA2": 12.5,
    "C1": 1234,
    "C2": 56,
    "THL1-TEMP": 21.46,
    "THL1-HUM": 48.2,
    "THL1-LUM": 320,
    "ENO ANALOG17": 12.34,
    "ENO ACTIONNEUR1": 1,
    "G1": {"Etat": "ON", "Valeur": 60},
    "PWM1": 50,
    "PWM2": 100,
    "PWM3": 50,
    "PWM4": 0,
    "PWM5": 0,
    "PWM6": 0,
    "PWM7": 0,
    "PWM8": 80,
    "VR1-1": 0,
    "VR1-2": 100,
    "FP1 Zone 1": "Eco",
}

SYSTEM_DATA: dict[str, Any] = {
    "uptime": 3600,
    "load": 1234,
    "last_boot": datetime(2026, 10, 27, 11, 0, tzinfo=UTC),
    "clock_offset": 3,
    "clock_in_sync": True,
    "mac": MAC,
}


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return the snapshot assertion with the Home Assistant serializer."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable the custom integrations in every test."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the config entry of an IPX800 imported from YAML."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        unique_id=f"{DOMAIN}, {NAME}",
        data=deepcopy(ENTRY_DATA),
    )


@pytest.fixture
def mock_ipx800() -> Generator[MagicMock]:
    """Mock the polling client of the IPX800."""
    client = MagicMock()
    client.host = HOST
    client.port = 80
    client.global_get = AsyncMock(return_value=deepcopy(IPX_DATA))
    with patch("custom_components.ipx800v4.IPX800", return_value=client):
        yield client


@pytest.fixture
def mock_command_client() -> Generator[MagicMock]:
    """Mock the command client of the IPX800."""
    client = MagicMock()
    client.host = HOST
    client.port = 80
    client.request_api = AsyncMock(return_value={"status": "Success"})
    client.request_cgi = AsyncMock(return_value="Success")
    with patch("custom_components.ipx800v4.IpxCommandClient", return_value=client):
        yield client


@pytest.fixture
def mock_system() -> Generator[MagicMock]:
    """Mock the reader of the XML diagnostics."""
    system = MagicMock()
    system.async_get = AsyncMock(return_value=deepcopy(SYSTEM_DATA))
    with patch("custom_components.ipx800v4.IpxSystemData", return_value=system):
        yield system


@pytest.fixture
def mock_clients(
    mock_ipx800: MagicMock, mock_command_client: MagicMock, mock_system: MagicMock
) -> MagicMock:
    """Mock every client of the IPX800, return the polling client."""
    return mock_ipx800
