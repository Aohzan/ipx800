"""Entry setup builds the pypx800 client for the configured devices."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import test_coordinator
from custom_components.ipx800v4 import async_setup_entry
from custom_components.ipx800v4.const import COORDINATOR, SYSTEM_COORDINATOR


class SetupTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_coordinator.ReadRecoveryTests.asyncSetUp
    asyncTearDown = test_coordinator.ReadRecoveryTests.asyncTearDown
    make_coordinator = test_coordinator.ReadRecoveryTests.make_coordinator

    async def setup_entry(self, device_types):
        """Set up an entry with a sensor per device type, return IPX800 kwargs."""
        template, _ = self.make_coordinator()
        hass, entry = template.hass, template.config_entry
        hass.data = {}
        hass.config_entries = SimpleNamespace(async_forward_entry_setups=AsyncMock())
        entry.entry_id = "ipx"
        entry.data = {
            "host": "192.0.2.1", "port": 80, "api_key": "test",
            "name": "IPX", "scan_interval": 300,
            "devices": [
                {"name": device_type, "component": "sensor",
                 "type": device_type, "id": 1}
                for device_type in device_types
            ],
        }
        entry.options = {}
        ipx = Mock(host="192.0.2.1", global_get=AsyncMock(return_value={}))
        system = Mock(async_get=AsyncMock(return_value={}))
        with (
            patch("custom_components.ipx800v4.async_get_clientsession"),
            patch("custom_components.ipx800v4.dr.async_get", return_value=Mock()),
            patch("custom_components.ipx800v4.IPX800", return_value=ipx) as factory,
            patch("custom_components.ipx800v4.IpxSystemData", return_value=system),
        ):
            await async_setup_entry(hass, entry)
        runtime = hass.data["ipx800v4"]["ipx"]
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


if __name__ == "__main__":
    unittest.main()
