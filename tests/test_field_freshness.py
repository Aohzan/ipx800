"""Bounded missing-field recovery using the real HA coordinator scheduler."""

import asyncio
import unittest
from time import monotonic
from unittest.mock import Mock, patch

import test_coordinator
from pypx800 import Ipx800CannotConnectError

from custom_components.ipx800v4.light import XPWMRGBLight
from custom_components.ipx800v4.switch import RelaySwitch


class FieldFreshnessTests(unittest.IsolatedAsyncioTestCase):
    """Exercise omissions independently of global read failures and pushes."""

    asyncSetUp = test_coordinator.ReadRecoveryTests.asyncSetUp
    asyncTearDown = test_coordinator.ReadRecoveryTests.asyncTearDown
    make_coordinator = test_coordinator.ReadRecoveryTests.make_coordinator
    assert_next_read = test_coordinator.ReadRecoveryTests.assert_next_read

    async def setup_fields(self, interval=300, keys=("R1", "PWM1", "PWM2", "PWM3")):
        coordinator, reader = self.make_coordinator(interval)
        reader.return_value = {key: 1 for key in keys}
        await coordinator.async_config_entry_first_refresh()
        coordinator.register_fields(keys)
        coordinator.async_add_listener(Mock())
        return coordinator, reader

    async def test_third_omission_expires_only_dependent_entities(self):
        for interval in (300, 10):
            with self.subTest(interval=interval):
                coordinator, reader = await self.setup_fields(interval)
                rgb = XPWMRGBLight.__new__(XPWMRGBLight)
                rgb.coordinator, rgb._ids = coordinator, [1, 2, 3]
                relay = RelaySwitch.__new__(RelaySwitch)
                relay.coordinator, relay._id = coordinator, 1
                receipt = coordinator.field_receipt_times["PWM1"]
                reader.return_value = {"R1": 0, "PWM2": 0, "PWM3": 0}
                for omission in range(1, 5):
                    await coordinator.async_refresh()
                    self.assertTrue(coordinator.last_update_success)
                    self.assertEqual(coordinator.consecutive_failures, 0)
                    self.assertTrue(relay.available)
                    self.assertFalse(relay.is_on)
                    self.assertEqual(rgb.available, omission < 3)
                    self.assertEqual(coordinator.data["PWM2"], 0)
                    self.assert_next_read(
                        coordinator, min(interval, 15) if omission < 3 else interval
                    )
                    if omission < 3:
                        self.assertEqual(
                            coordinator.field_receipt_times["PWM1"], receipt
                        )
                self.assertNotIn("PWM1", coordinator.data)
                self.assertFalse(coordinator._missing_fields)
                reader.return_value["PWM1"] = 0
                await coordinator.async_refresh()
                self.assertTrue(rgb.available)
                self.assertFalse(rgb.is_on)

    async def test_transient_omission_and_never_seen_or_unused_fields(self):
        coordinator, reader = await self.setup_fields(keys=("R1",))
        coordinator.register_fields(("D1",))
        reader.return_value = {"R1": False, "UNUSED": 42}
        await coordinator.async_refresh()
        reader.return_value = {}
        await coordinator.async_refresh()
        self.assertTrue(coordinator.fields_available("R1"))
        self.assertFalse(coordinator.fields_available("D1"))
        self.assertEqual(set(coordinator._missing_fields), {"R1"})
        self.assertNotIn("UNUSED", coordinator.data)
        reader.return_value = {"R1": 1}
        await coordinator.async_refresh()
        self.assertFalse(coordinator._missing_fields)
        self.assert_next_read(coordinator, 300)

    async def test_deadline_starts_at_omission_and_failed_reads_do_not_count(self):
        coordinator, reader = await self.setup_fields(keys=("R1", "D1"))
        original_time = monotonic()
        with patch(
            "custom_components.ipx800v4.coordinator.monotonic",
            return_value=original_time + 300,
        ):
            reader.return_value = {"D1": 0}
            await coordinator.async_refresh()
            self.assertTrue(coordinator.fields_available("R1"))
            started, count = coordinator._missing_fields["R1"]
            self.assertEqual(started, original_time + 300)
            self.assertEqual(count, 1)
            reader.side_effect = Ipx800CannotConnectError()
            await coordinator.async_refresh()
            self.assertEqual(coordinator._missing_fields["R1"], (started, 1))
        listener = Mock()
        coordinator.async_add_listener(listener)
        with patch(
            "custom_components.ipx800v4.coordinator.monotonic",
            return_value=started + 30,
        ):
            coordinator._expire_fields()
        self.assertNotIn("R1", coordinator.data)
        self.assertTrue(coordinator.fields_available("D1"))
        listener.assert_called_once()
        self.assert_next_read(coordinator, 15)  # Global recovery remains scheduled.

    async def test_expiry_preserves_pending_recovery_read(self):
        coordinator, reader = await self.setup_fields(keys=("R1", "D1"))
        reader.return_value = {"D1": 0}
        await coordinator.async_refresh()
        started, _ = coordinator._missing_fields["R1"]
        with patch(
            "custom_components.ipx800v4.coordinator.monotonic",
            return_value=started + 15,
        ):
            await coordinator.async_refresh()
        pending = self.assert_next_read(coordinator, 15)
        with patch(
            "custom_components.ipx800v4.coordinator.monotonic",
            return_value=started + 30,
        ):
            coordinator._expire_fields()
        self.assertFalse(coordinator.fields_available("R1"))
        self.assertFalse(pending.cancelled())
        self.assertIs(coordinator._unsub_refresh.__self__, pending)
        reader.return_value = {"R1": 1, "D1": 0}
        await coordinator.async_refresh()
        self.assertTrue(coordinator.fields_available("R1"))
        self.assert_next_read(coordinator, 300)

    async def test_real_timer_expires_without_another_read(self):
        coordinator, reader = await self.setup_fields(interval=0.025, keys=("R1",))
        coordinator.config_entry.pref_disable_polling = True
        reader.return_value = {}
        await coordinator.async_refresh()
        listener = Mock()
        coordinator.async_add_listener(listener)
        count = reader.await_count
        await asyncio.sleep(0.08)
        self.assertFalse(coordinator.fields_available("R1"))
        self.assertFalse(coordinator._missing_fields)
        self.assertEqual(reader.await_count, count)
        listener.assert_called_once()

    async def test_push_refreshes_only_supplied_fields(self):
        coordinator, reader = await self.setup_fields(keys=("R1", "D1"))
        reader.return_value = {}
        await coordinator.async_refresh()
        omission = coordinator._missing_fields["D1"]
        coordinator.async_apply_push({"R1": 0})
        self.assertNotIn("R1", coordinator._missing_fields)
        self.assertEqual(coordinator._missing_fields["D1"], omission)
        self.assertTrue(coordinator.fields_available("R1", "D1"))
        await coordinator.async_refresh()
        self.assertEqual(coordinator._missing_fields["R1"][1], 1)
        self.assertEqual(coordinator._missing_fields["D1"][1], 2)
        await coordinator.async_refresh()
        self.assertTrue(coordinator.fields_available("R1"))
        self.assertFalse(coordinator.fields_available("D1"))
        coordinator.async_apply_push({"D1": False})
        self.assertTrue(coordinator.fields_available("D1"))

    async def test_push_during_incomplete_read_wins(self):
        coordinator, reader = await self.setup_fields(keys=("R1", "D1"))
        entered, release = asyncio.Event(), asyncio.Event()

        async def read():
            entered.set()
            await release.wait()
            return {}

        reader.side_effect = read
        task = asyncio.create_task(coordinator.async_refresh())
        await entered.wait()
        coordinator.async_apply_push({"R1": 0})
        pushed_at = coordinator.field_receipt_times["R1"]
        release.set()
        await task
        self.assertEqual(coordinator.data["R1"], 0)
        self.assertEqual(coordinator.field_receipt_times["R1"], pushed_at)
        self.assertNotIn("R1", coordinator._missing_fields)
        self.assertIn("D1", coordinator._missing_fields)

    async def test_expiry_during_inflight_read_does_not_restart_episode(self):
        coordinator, reader = await self.setup_fields(keys=("R1", "D1"))
        reader.return_value = {"D1": 0}
        await coordinator.async_refresh()
        started, _ = coordinator._missing_fields["R1"]
        entered, release = asyncio.Event(), asyncio.Event()

        async def read():
            entered.set()
            await release.wait()
            return {"D1": 1}

        reader.side_effect = read
        task = asyncio.create_task(coordinator.async_refresh())
        await entered.wait()
        with patch(
            "custom_components.ipx800v4.coordinator.monotonic",
            return_value=started + 30,
        ):
            coordinator._expire_fields()
        self.assertFalse(coordinator.fields_available("R1"))
        self.assertIsNone(coordinator._unsub_refresh)
        release.set()
        await task
        self.assertFalse(coordinator._missing_fields)
        self.assertEqual(coordinator.data, {"D1": 1})
        self.assert_next_read(coordinator, 300)

    async def test_invalid_fields_and_nested_dimmer_data(self):
        coordinator, reader = await self.setup_fields(keys=("R1",))
        coordinator.register_fields(("G1",))
        reader.return_value = {"R1": 0, "G1": {"Etat": "OFF", "Valeur": 0}}
        await coordinator.async_refresh()
        for invalid in (None, float("nan"), ""):
            reader.return_value = {"R1": invalid, "G1": {"Etat": "ON"}}
            await coordinator.async_refresh()
        self.assertFalse(coordinator.fields_available("R1"))
        self.assertFalse(coordinator.fields_available("G1"))
        reader.return_value = {"R1": False, "G1": {"Etat": "OFF", "Valeur": 0}}
        await coordinator.async_refresh()
        self.assertTrue(coordinator.fields_available("R1", "G1"))

    async def test_shared_fields_and_two_controllers_cleanup(self):
        first, reader = await self.setup_fields(keys=("R1",))
        second, _ = await self.setup_fields(keys=("R1",))
        first.register_fields(("R1",))
        first.unregister_fields(("R1",))
        reader.return_value = {}
        await first.async_refresh()
        timer = first._freshness_expiry
        self.assertTrue(first._missing_fields)
        await first.async_shutdown()
        self.assertTrue(timer.cancelled())
        self.assertFalse(first._required_fields)
        self.assertFalse(first.field_receipt_times)
        await second.async_refresh()
        self.assertTrue(second.fields_available("R1"))
        self.assert_next_read(second, 300)


if __name__ == "__main__":
    unittest.main()
