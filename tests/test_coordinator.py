"""Regression coverage for bounded IPX read recovery.

Run with the project's dependencies installed: python -m unittest discover -s tests
"""

import asyncio
from datetime import timedelta
import logging
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from pypx800 import (
    Ipx800CannotConnectError,
    Ipx800InvalidAuthError,
    Ipx800RequestError,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.debounce import Debouncer

from custom_components.ipx800v4.coordinator import IpxDataUpdateCoordinator


class ReadRecoveryTests(unittest.IsolatedAsyncioTestCase):
    """Exercise HA's polling timer, debounce and listener handling."""

    async def asyncSetUp(self):
        self.coordinators = []
        self.tasks = []

    async def asyncTearDown(self):
        for coordinator in self.coordinators:
            await coordinator.async_shutdown()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

    def make_coordinator(self, interval=300):
        loop = asyncio.get_running_loop()

        def create_task(coro, *args, **kwargs):
            task = loop.create_task(coro)
            self.tasks.append(task)
            return task

        hass = SimpleNamespace(
            loop=loop,
            is_stopping=False,
            async_create_task=create_task,
            async_create_background_task=create_task,
            async_run_hass_job=lambda job, **kwargs: create_task(job.target()),
        )
        entry = Mock(
            pref_disable_polling=False,
            state=ConfigEntryState.SETUP_IN_PROGRESS,
        )
        entry.async_create_background_task.side_effect = (
            lambda hass, coro, **kwargs: create_task(coro)
        )
        reader = AsyncMock(return_value={"R1": 1, "system": {"load": 10}})
        logger = logging.getLogger("ipx800_test")
        coordinator = IpxDataUpdateCoordinator(
            hass,
            logger,
            name=f"Test IPX {len(self.coordinators)} (192.0.2.1)",
            config_entry=entry,
            update_method=reader,
            update_interval=timedelta(seconds=interval),
            request_refresh_debouncer=Debouncer(
                hass, logger, cooldown=0.5, immediate=False
            ),
        )
        self.coordinators.append(coordinator)
        return coordinator, reader

    def assert_next_read(self, coordinator, delay):
        timer = coordinator._unsub_refresh.__self__
        remaining = timer.when() - asyncio.get_running_loop().time()
        self.assertAlmostEqual(remaining, delay, delta=1)
        return timer

    async def test_bounded_failures_and_recovery(self):
        for interval in (300, 10):
            with self.subTest(interval=interval):
                coordinator, reader = self.make_coordinator(interval)
                self.assertFalse(coordinator.data_available)
                await coordinator.async_config_entry_first_refresh()
                availability = []
                coordinator.async_add_listener(
                    lambda: availability.append(coordinator.data_available)
                )
                snapshot = coordinator.data
                timestamp = coordinator.last_successful_read
                reader.side_effect = Ipx800CannotConnectError()
                for failure in (1, 2, 3, 4):
                    await coordinator.async_refresh()
                    self.assertFalse(coordinator.last_update_success)
                    self.assertEqual(coordinator.consecutive_failures, failure)
                    self.assertIs(coordinator.data, snapshot)
                    self.assertEqual(coordinator.last_successful_read, timestamp)
                    self.assertEqual(coordinator.data_available, failure < 3)
                    self.assert_next_read(
                        coordinator, min(interval, 15) if failure < 3 else interval
                    )
                self.assertEqual(availability, [True, False])
                reader.side_effect = None
                await coordinator.async_refresh()
                self.assertTrue(coordinator.last_update_success)
                self.assertTrue(coordinator.data_available)
                self.assertEqual(coordinator.consecutive_failures, 0)
                self.assert_next_read(coordinator, interval)
                self.assertEqual(availability, [True, False, True])

    async def test_push_recovers_before_retry_and_batches(self):
        for failures in (1, 2):
            with self.subTest(failures=failures):
                coordinator, reader = self.make_coordinator()
                await coordinator.async_config_entry_first_refresh()
                listener = Mock()
                coordinator.async_add_listener(listener)
                reader.side_effect = Ipx800CannotConnectError()
                for _ in range(failures):
                    await coordinator.async_refresh()
                pending = self.assert_next_read(coordinator, 15)
                reader.side_effect = None
                count = reader.await_count
                for _ in range(10):
                    await coordinator.async_request_refresh()
                self.assertEqual(reader.await_count, count)
                await asyncio.sleep(0.6)
                self.assertEqual(reader.await_count, count + 1)
                self.assertTrue(pending.cancelled())
                self.assertTrue(coordinator.data_available)
                self.assertEqual(coordinator.consecutive_failures, 0)
                self.assert_next_read(coordinator, 300)
                # The debounce's remaining cooldown must not execute another read.
                await asyncio.sleep(0.6)
                self.assertEqual(reader.await_count, count + 1)

    async def test_startup_failure_uses_setup_retry(self):
        coordinator, reader = self.make_coordinator()
        reader.side_effect = Ipx800CannotConnectError()
        with self.assertRaises(ConfigEntryNotReady):
            await coordinator.async_config_entry_first_refresh()
        self.assertFalse(coordinator.data_available)
        self.assertIsNone(coordinator.last_successful_read)
        self.assertIsNone(coordinator._unsub_refresh)
        self.assertEqual(reader.await_count, 1)

    async def test_definitive_errors_do_not_retain_data(self):
        for error in (Ipx800InvalidAuthError, Ipx800RequestError, ValueError):
            with self.subTest(error=error):
                coordinator, reader = self.make_coordinator()
                await coordinator.async_config_entry_first_refresh()
                listener = Mock()
                coordinator.async_add_listener(listener)
                reader.side_effect = Ipx800CannotConnectError()
                await coordinator.async_refresh()
                self.assertTrue(coordinator.data_available)
                pending = self.assert_next_read(coordinator, 15)
                reader.side_effect = error()
                await coordinator.async_refresh()
                self.assertFalse(coordinator.data_available)
                self.assertTrue(pending.cancelled())
                self.assertEqual(listener.call_count, 2)
                if error is Ipx800InvalidAuthError:
                    # HA 2026.9 renamed the reauthentication helper.
                    self.assertEqual(
                        coordinator.config_entry.async_start_reauth.call_count
                        + coordinator.config_entry.async_start_reauth_if_available.call_count,
                        1,
                    )
                    self.assertIsNone(coordinator._unsub_refresh)
                else:
                    self.assert_next_read(coordinator, 300)

    async def test_startup_auth_error_is_not_setup_retry(self):
        coordinator, reader = self.make_coordinator()
        reader.side_effect = Ipx800InvalidAuthError()
        with self.assertRaises(ConfigEntryAuthFailed):
            await coordinator.async_config_entry_first_refresh()

    async def test_shutdown_does_not_affect_other_controller(self):
        first, reader = self.make_coordinator()
        second, other_reader = self.make_coordinator(10)
        for coordinator in (first, second):
            await coordinator.async_config_entry_first_refresh()
            coordinator.async_add_listener(Mock())
        reader.side_effect = Ipx800CannotConnectError()
        await first.async_refresh()
        pending = self.assert_next_read(first, 15)
        await first.async_request_refresh()
        await first.async_shutdown()
        await asyncio.sleep(0.6)
        self.assertTrue(pending.cancelled())
        self.assertEqual(reader.await_count, 2)
        await first.async_refresh()
        self.assertEqual(reader.await_count, 2)
        await second.async_refresh()
        self.assertEqual(other_reader.await_count, 2)
        self.assertTrue(second.data_available)
        self.assert_next_read(second, 10)

    async def test_shutdown_during_read_does_not_reschedule(self):
        coordinator, reader = self.make_coordinator()
        await coordinator.async_config_entry_first_refresh()
        coordinator.async_add_listener(Mock())
        entered = asyncio.Event()
        release = asyncio.Event()

        async def blocked_read():
            entered.set()
            await release.wait()
            raise Ipx800CannotConnectError()

        reader.side_effect = blocked_read
        task = asyncio.create_task(coordinator.async_refresh())
        await entered.wait()
        await coordinator.async_shutdown()
        release.set()
        await task
        self.assertIsNone(coordinator._unsub_refresh)

    async def test_simultaneous_refreshes_are_serialized(self):
        coordinator, reader = self.make_coordinator()
        await coordinator.async_config_entry_first_refresh()
        coordinator.async_add_listener(Mock())
        active = 0
        maximum = 0

        async def slow_read():
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {"R1": 1}

        reader.side_effect = slow_read
        await asyncio.gather(*(coordinator.async_refresh() for _ in range(5)))
        self.assertEqual(maximum, 1)


if __name__ == "__main__":
    unittest.main()
