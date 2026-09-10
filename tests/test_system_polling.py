"""XML diagnostics have a polling schedule independent of I/O refreshes."""

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import test_coordinator
from custom_components.ipx800v4 import async_setup_entry
from custom_components.ipx800v4.const import COORDINATOR, SYSTEM_COORDINATOR
from custom_components.ipx800v4.sensor import IpxLoadSensor


class SystemPollingTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_coordinator.ReadRecoveryTests.asyncSetUp
    asyncTearDown = test_coordinator.ReadRecoveryTests.asyncTearDown
    make_coordinator = test_coordinator.ReadRecoveryTests.make_coordinator

    async def test_pushes_do_not_read_xml_or_postpone_its_timer(self):
        template, _ = self.make_coordinator()
        hass, entry = template.hass, template.config_entry
        hass.data = {}
        hass.config_entries = SimpleNamespace(async_forward_entry_setups=AsyncMock())
        entry.entry_id = "ipx"
        entry.data = {
            "host": "192.0.2.1", "port": 80, "api_key": "test",
            "name": "IPX", "scan_interval": 300, "devices": [],
        }
        entry.options = {}
        ipx = Mock(host="192.0.2.1", global_get=AsyncMock(return_value={"R1": 1}))
        system = Mock(async_get=AsyncMock(return_value={"load": 10}))
        with (
            patch("custom_components.ipx800v4.async_get_clientsession"),
            patch("custom_components.ipx800v4.dr.async_get", return_value=Mock()),
            patch("custom_components.ipx800v4.IPX800", return_value=ipx),
            patch("custom_components.ipx800v4.IpxSystemData", return_value=system),
        ):
            await async_setup_entry(hass, entry)
        runtime = hass.data["ipx800v4"]["ipx"]
        io, xml = runtime[COORDINATOR], runtime[SYSTEM_COORDINATOR]
        self.coordinators.extend((io, xml))
        io.async_add_listener(Mock())
        xml.async_add_listener(Mock())
        timer = xml._unsub_refresh.__self__
        self.assertEqual(xml.update_interval.total_seconds(), 300)
        system.async_get.assert_awaited_once()
        diagnostic = IpxLoadSensor(ipx, xml, "load")
        self.assertTrue(diagnostic.available)
        self.assertEqual(diagnostic.native_value, 10)
        for _ in range(5):
            io.async_apply_push({"R1": 0})
            await io.async_request_refresh()
        await asyncio.sleep(0.6)
        self.assertGreater(ipx.global_get.await_count, 1)
        system.async_get.assert_awaited_once()
        self.assertIs(xml._unsub_refresh.__self__, timer)
        self.assertFalse(timer.cancelled())

        # A slow timer-driven XML read does not hold the I/O refresh lock.
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_xml():
            entered.set()
            await release.wait()
            return {}  # Failed XML snapshot affects diagnostics only.

        system.async_get.side_effect = slow_xml
        timer.cancel()
        task = asyncio.create_task(xml._handle_refresh_interval())
        self.tasks.append(task)
        await entered.wait()
        try:
            await asyncio.wait_for(io.async_refresh(), timeout=1)
            self.assertTrue(io.fields_available("R1"))
        finally:
            release.set()
            await task
        self.assertFalse(diagnostic.available)
        self.assertTrue(io.fields_available("R1"))
        next_timer = xml._unsub_refresh.__self__
        await xml.async_shutdown()
        self.assertTrue(next_timer.cancelled())
