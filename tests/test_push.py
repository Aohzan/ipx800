"""Direct push mapping, atomic validation, freshness and read races."""

import asyncio
from time import monotonic
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from aiohttp import web
from pypx800 import Ipx800CannotConnectError

from custom_components.ipx800v4.binary_sensor import DigitalInBinarySensor
from custom_components.ipx800v4.light import XPWMLight
from custom_components.ipx800v4.sensor import XTHLSensor
from custom_components.ipx800v4.switch import RelaySwitch, VirtualOutSwitch
from custom_components.ipx800v4.const import COORDINATOR, DOMAIN
from custom_components.ipx800v4.push import (
    IpxRequestView, IpxRequestDataView, IpxRequestBulkUpdateView,
)
import test_coordinator


def entity(cls, coordinator, entity_id, field_id=1, invert=False):
    """Instantiate state readers without creating command clients."""
    result = cls.__new__(cls)
    result.coordinator = coordinator
    result.entity_id = entity_id
    result._id = field_id
    result._invert_value = invert
    result._ipx_type = "digitalin" if cls is DigitalInBinarySensor else "relay"
    return result


class PushTests(unittest.IsolatedAsyncioTestCase):
    """Use the real coordinator and platform state readers."""

    asyncSetUp = test_coordinator.ReadRecoveryTests.asyncSetUp
    asyncTearDown = test_coordinator.ReadRecoveryTests.asyncTearDown
    make_coordinator = test_coordinator.ReadRecoveryTests.make_coordinator
    assert_next_read = test_coordinator.ReadRecoveryTests.assert_next_read

    async def test_push_does_not_reset_failures_or_recovery_timer(self):
        coordinator, reader = self.make_coordinator()
        await coordinator.async_config_entry_first_refresh()
        coordinator.async_add_listener(Mock())
        relay = entity(RelaySwitch, coordinator, "switch.renamed")
        reader.side_effect = Ipx800CannotConnectError()
        await coordinator.async_refresh()
        pending = self.assert_next_read(coordinator, 15)
        timestamp = coordinator.last_successful_read
        IpxRequestView()._apply(coordinator, [(relay, "off")])
        self.assertEqual(coordinator.data["R1"], 0)
        self.assertFalse(relay.is_on)
        coordinator.async_update_listeners()
        self.assertFalse(relay.is_on)
        self.assertFalse(coordinator.last_update_success)
        self.assertEqual(coordinator.consecutive_failures, 1)
        self.assertEqual(coordinator.last_successful_read, timestamp)
        self.assertFalse(pending.cancelled())
        self.assertEqual(set(coordinator.field_push_times), {"R1"})
        for _ in range(2):
            await coordinator.async_refresh()
        self.assertTrue(relay.available)
        self.assertFalse(coordinator.data_available)
        self.assertFalse(coordinator.fields_available("system"))
        self.assertFalse(coordinator.fields_available("R1", "R2"))
        self.assertEqual(coordinator.consecutive_failures, 3)
        reader.side_effect = None
        await coordinator.async_refresh()
        self.assertTrue(relay.is_on)
        self.assertEqual(coordinator.field_push_times, {})
        self.assertEqual(coordinator.consecutive_failures, 0)

    async def test_expiry_and_shutdown(self):
        coordinator, reader = self.make_coordinator()
        await coordinator.async_config_entry_first_refresh()
        listener = Mock()
        coordinator.async_add_listener(listener)
        reader.side_effect = Ipx800CannotConnectError()
        for _ in range(3):
            await coordinator.async_refresh()
        coordinator.async_apply_push({"R1": 0})
        self.assertTrue(coordinator.fields_available("R1"))
        with patch("custom_components.ipx800v4.coordinator.monotonic",
                   return_value=monotonic() + coordinator.push_ttl + 1):
            coordinator._expire_fields()
        self.assertFalse(coordinator.fields_available("R1"))
        self.assertEqual(coordinator.field_push_times, {})
        coordinator.async_apply_push({"R1": 1})
        timer = coordinator._freshness_expiry
        await coordinator.async_shutdown()
        self.assertTrue(timer.cancelled())

    async def test_push_during_full_read_wins_then_next_read_reconciles(self):
        coordinator, reader = self.make_coordinator()
        await coordinator.async_config_entry_first_refresh()
        entered, release = asyncio.Event(), asyncio.Event()

        async def blocked_read():
            entered.set()
            await release.wait()
            return {"R1": 1, "R2": 0}

        reader.side_effect = blocked_read
        task = asyncio.create_task(coordinator.async_refresh())
        await entered.wait()
        coordinator.async_apply_push({"R1": 0})
        release.set()
        await task
        self.assertEqual(coordinator.data, {"R1": 0, "R2": 0})
        reader.side_effect = None
        await coordinator.async_refresh()
        self.assertEqual(coordinator.data["R1"], 1)

    async def test_platform_conversions_and_atomic_rejection(self):
        coordinator, reader = self.make_coordinator()
        await coordinator.async_config_entry_first_refresh()
        inverted = entity(DigitalInBinarySensor, coordinator, "binary_sensor.d", invert=True)
        switch = entity(VirtualOutSwitch, coordinator, "switch.v", invert=True)
        pwm = entity(XPWMLight, coordinator, "light.pwm")
        thl = entity(XTHLSensor, coordinator, "sensor.temp")
        thl._req_type = "TEMP"
        view = IpxRequestView()
        view._apply(coordinator, [(inverted, "on"), (switch, "on"),
                                  (pwm, "42"), (thl, "21.5")])
        self.assertEqual(coordinator.data["D1"], 0)
        self.assertTrue(inverted.is_on)
        self.assertTrue(switch.is_on)  # Switch platform does not invert values.
        self.assertEqual(coordinator.data["PWM1"], 42)
        self.assertEqual(thl.native_value, 21.5)
        before = dict(coordinator.data)
        times = dict(coordinator.field_push_times)
        for invalid, value in [(inverted, "bad"), (pwm, "101"),
                               (pwm, "on"), (thl, "nan"), (thl, "inf")]:
            with self.subTest(value=value), self.assertRaises(web.HTTPBadRequest):
                view._apply(coordinator, [(inverted, "off"), (invalid, value)])
            self.assertEqual(coordinator.data, before)
            self.assertEqual(coordinator.field_push_times, times)
        with self.assertRaises(web.HTTPBadRequest):
            view._apply(coordinator, [(inverted, "on"), (inverted, "off")])

    async def test_push_during_recovery_read_keeps_unrelated_cached_availability(self):
        coordinator, reader = self.make_coordinator()
        await coordinator.async_config_entry_first_refresh()
        reader.side_effect = Ipx800CannotConnectError()
        await coordinator.async_refresh()
        entered, release = asyncio.Event(), asyncio.Event()

        async def blocked_failure():
            entered.set()
            await release.wait()
            raise Ipx800CannotConnectError()

        reader.side_effect = blocked_failure
        task = asyncio.create_task(coordinator.async_refresh())
        await entered.wait()
        coordinator.async_apply_push({"D1": 1})
        self.assertTrue(coordinator.fields_available("R1"))
        self.assertEqual(coordinator.consecutive_failures, 1)
        release.set()
        await task
        self.assertTrue(coordinator.fields_available("R1"))
        self.assertEqual(coordinator.consecutive_failures, 2)

    async def test_registry_renames_cross_instance_and_bad_batches(self):
        coordinator, reader = self.make_coordinator()
        await coordinator.async_config_entry_first_refresh()
        coordinator.config_entry.entry_id = "a"
        relay = entity(RelaySwitch, coordinator, "switch.renamed")
        coordinator.push_entities["stable-id"] = relay
        entries = {
            "switch.renamed": SimpleNamespace(
                entity_id="switch.renamed", platform=DOMAIN,
                config_entry_id="a", unique_id="stable-id"),
            "switch.other": SimpleNamespace(
                entity_id="switch.other", platform=DOMAIN,
                config_entry_id="b", unique_id="stable-id"),
            "switch.foreign": SimpleNamespace(
                entity_id="switch.foreign", platform="other",
                config_entry_id="a", unique_id="stable-id"),
        }
        registry = SimpleNamespace(async_get=entries.get)
        request = SimpleNamespace(app={"hass": object()})
        with patch("custom_components.ipx800v4.push.er.async_get", return_value=registry):
            view = IpxRequestView()
            view._entry = Mock(return_value={COORDINATOR: coordinator})
            self.assertEqual((await view.get(request, "switch.renamed", "off")).status, 200)
            self.assertFalse(relay.is_on)
            for target in ("switch.old_name", "switch.other", "switch.foreign"):
                with self.assertRaises(web.HTTPNotFound):
                    await view.get(request, target, "on")
            batch = IpxRequestDataView()
            batch._entry = view._entry
            for payload in ("switch.renamed=on&broken", "switch.renamed=",
                            "switch.renamed=on&switch.other=on"):
                with self.assertRaises(web.HTTPClientError):
                    await batch.get(request, payload)
                self.assertFalse(relay.is_on)
            bulk = IpxRequestBulkUpdateView()
            bulk._entry = view._entry
            with patch("custom_components.ipx800v4.push.er.async_entries_for_config_entry",
                       return_value=[entries["switch.renamed"]]):
                self.assertEqual((await bulk.get(request, "relay", "1")).status, 200)
                self.assertTrue(relay.is_on)
                with self.assertRaises(web.HTTPBadRequest):
                    await bulk.get(request, "relay", "0x")
                self.assertTrue(relay.is_on)

    async def test_bulk_inversion_and_partial_field_recovery(self):
        coordinator, reader = self.make_coordinator()
        await coordinator.async_config_entry_first_refresh()
        coordinator.config_entry.entry_id = "a"
        inverted = entity(DigitalInBinarySensor, coordinator, "binary_sensor.renamed",
                          invert=True)
        second = entity(DigitalInBinarySensor, coordinator, "binary_sensor.second", 2)
        coordinator.register_fields(inverted.required_keys)
        coordinator.register_fields(second.required_keys)
        coordinator.push_entities.update(first=inverted, second=second)
        registry_entries = [
            SimpleNamespace(entity_id=item.entity_id, platform=DOMAIN, unique_id=key)
            for key, item in coordinator.push_entities.items()
        ]
        reader.side_effect = Ipx800CannotConnectError()
        for _ in range(3):
            await coordinator.async_refresh()
        view = IpxRequestBulkUpdateView()
        view._entry = Mock(return_value={COORDINATOR: coordinator})
        with patch("custom_components.ipx800v4.push.er.async_get"), patch(
            "custom_components.ipx800v4.push.er.async_entries_for_config_entry",
            return_value=registry_entries,
        ):
            request = SimpleNamespace(app={"hass": object()})
            await view.get(request, "digitalin", "0")
            self.assertTrue(inverted.is_on)
            self.assertTrue(inverted.available)
            self.assertFalse(second.available)
            self.assertFalse(coordinator.fields_available("D1", "D2"))
            self.assertEqual(set(coordinator.field_push_times), {"D1"})
            await view.get(request, "digitalin", "01")
            self.assertTrue(coordinator.fields_available("D1", "D2"))
            self.assertEqual(coordinator.consecutive_failures, 3)
        reader.side_effect = None
        # Successful omissions retain pushed values only for the bounded grace.
        for omission in (1, 2, 3):
            await coordinator.async_refresh()
            self.assertEqual(inverted.available, omission < 3)
            self.assertEqual(second.available, omission < 3)
        self.assertEqual(coordinator.field_push_times, {})
