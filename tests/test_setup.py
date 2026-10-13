"""Entry setup builds the pypx800 client for the configured devices."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import test_coordinator
from custom_components.ipx800v4 import async_setup_entry
from custom_components.ipx800v4.const import COORDINATOR, SYSTEM_COORDINATOR
from custom_components.ipx800v4.switch import XENOSwitch


class SetupTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_coordinator.ReadRecoveryTests.asyncSetUp
    asyncTearDown = test_coordinator.ReadRecoveryTests.asyncTearDown
    make_coordinator = test_coordinator.ReadRecoveryTests.make_coordinator

    async def setup_entry(self, device_types, component="sensor"):
        """Set up an entry with an entity per device type, return IPX800 kwargs."""
        template, _ = self.make_coordinator()
        hass, entry = template.hass, template.config_entry
        hass.data = {}
        hass.config_entries = SimpleNamespace(async_forward_entry_setups=AsyncMock())
        entry.entry_id = "ipx"
        entry.data = {
            "host": "192.0.2.1", "port": 80, "api_key": "test",
            "name": "IPX", "scan_interval": 300,
            "devices": [
                {"name": device_type, "component": component,
                 "type": device_type, "id": 1}
                for device_type in device_types
            ],
        }
        entry.options = {}
        ipx = Mock(host="192.0.2.1", global_get=AsyncMock(return_value={}))
        system = Mock(async_get=AsyncMock(return_value={}))
        self.registry = Mock()
        with (
            patch("custom_components.ipx800v4.async_get_clientsession"),
            patch("custom_components.ipx800v4.dr.async_get", return_value=self.registry),
            patch("custom_components.ipx800v4.IPX800", return_value=ipx) as factory,
            patch("custom_components.ipx800v4.IpxSystemData", return_value=system),
        ):
            await async_setup_entry(hass, entry)
        runtime = self.runtime = hass.data["ipx800v4"]["ipx"]
        self.coordinators.extend((runtime[COORDINATOR], runtime[SYSTEM_COORDINATOR]))
        return factory.call_args.kwargs

    async def test_specific_devices_types_follow_configured_devices(self):
        for device_types, expected in (
            (["analogin"], []),
            (["counter"], ["counter"]),
            (["virtualanalogin"], ["virtualanalogin"]),
            (["virtualanalogin", "analogin", "counter"], ["counter", "virtualanalogin"]),
        ):
            with self.subTest(device_types=device_types):
                kwargs = await self.setup_entry(device_types)
                self.assertEqual(kwargs["specific_devices_types"], expected)

    async def test_devices_are_linked_to_the_controller_device(self):
        await self.setup_entry(["xeno"], component="switch")
        coordinator = self.runtime[COORDINATOR]
        controller = self.registry.async_get_or_create.return_value
        self.assertIs(coordinator.controller_device_id, controller.id)
        config = {"name": "Prise", "component": "switch", "type": "xeno",
                  "id": 1, "invert_value": False}
        ipx = Mock(host="192.0.2.1", port=80)
        for minor, expected in (
            (8, {"via_device_id": controller.id}),
            (7, {"via_device": ("ipx800v4", "192.0.2.1")}),
        ):
            with (
                self.subTest(minor=minor),
                patch("custom_components.ipx800v4.entity.MAJOR_VERSION", 2026),
                patch("custom_components.ipx800v4.entity.MINOR_VERSION", minor),
            ):
                device_info = XENOSwitch(config, ipx, coordinator).device_info
                links = {
                    key: device_info[key]
                    for key in ("via_device", "via_device_id")
                    if key in device_info
                }
                self.assertEqual(links, expected)


if __name__ == "__main__":
    unittest.main()
