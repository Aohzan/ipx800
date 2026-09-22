"""Regression cases from PR #86: alias intents, deadlines and refusals."""

import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.exceptions import HomeAssistantError
from pypx800 import Relay, XPWM, Ipx800RequestError
from test_commands import make_entity

from custom_components.ipx800v4.commands import IpxCommandClient
from custom_components.ipx800v4.cover import X4VRCover
from custom_components.ipx800v4.light import RelayLight, XPWMRGBWLight
from custom_components.ipx800v4.switch import RelaySwitch


class ReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_identical_aliases_waiting_for_output_both_succeed(self):
        first, first_write = make_entity(RelaySwitch)
        second, second_write = make_entity(RelayLight)
        second.coordinator = first.coordinator
        lock = first.coordinator.commands._locks.setdefault("R1", asyncio.Lock())
        await lock.acquire()
        tasks = [asyncio.create_task(e.async_turn_off()) for e in (first, second)]
        await asyncio.sleep(0)
        first_write.assert_not_awaited()
        second_write.assert_not_awaited()
        lock.release()
        await asyncio.gather(*tasks)
        first_write.assert_awaited_once()
        second_write.assert_awaited_once()

    async def test_identical_alias_during_backoff_does_not_cancel_retry(self):
        first, first_write = make_entity(RelaySwitch)
        second, second_write = make_entity(RelayLight)
        second.coordinator = first.coordinator
        first_write.side_effect = [TimeoutError(), None]

        async def backoff(delay):
            await second.async_turn_off()

        with patch(
            "custom_components.ipx800v4.commands.asyncio.sleep", side_effect=backoff
        ):
            await first.async_turn_off()
        self.assertEqual(first_write.await_count, 2)
        second_write.assert_awaited_once()

    async def test_same_op_after_opposite_does_not_revive_old_retry(self):
        first, first_write = make_entity(RelaySwitch, TimeoutError())
        second, _ = make_entity(RelayLight)
        second.coordinator = first.coordinator

        async def backoff(delay):
            await second.async_turn_off()
            await second.async_turn_on()

        with (
            patch(
                "custom_components.ipx800v4.commands.asyncio.sleep", side_effect=backoff
            ),
            self.assertRaisesRegex(
                HomeAssistantError, "turn on.*switch.test_ipx.*superseded"
            ),
        ):
            await first.async_turn_on()
        first_write.assert_awaited_once()

    async def test_identical_alias_failure_is_not_silently_reported_as_success(self):
        first, first_write = make_entity(RelaySwitch, TimeoutError())
        second, _ = make_entity(RelayLight)
        second.coordinator = first.coordinator

        async def backoff(delay):
            await second.async_turn_off()

        with (
            patch(
                "custom_components.ipx800v4.commands.asyncio.sleep", side_effect=backoff
            ),
            self.assertRaisesRegex(HomeAssistantError, "attempts: 3, retries: 2"),
        ):
            await first.async_turn_off()
        self.assertEqual(first_write.await_count, 3)

    async def test_disabled_replay_does_not_share_scenario_intent(self):
        first, first_write = make_entity(RelaySwitch)
        second, _ = make_entity(RelayLight)
        first._retry_commands = second._retry_commands = False
        second.coordinator = first.coordinator
        lock = first.coordinator.commands._locks.setdefault("R1", asyncio.Lock())
        await lock.acquire()
        tasks = [asyncio.create_task(e.async_turn_off()) for e in (first, second)]
        await asyncio.sleep(0)
        lock.release()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        self.assertIsInstance(results[0], HomeAssistantError)
        self.assertIn("superseded", str(results[0]))
        self.assertIsNone(results[1])
        first_write.assert_not_awaited()

    async def test_authentication_has_context_status_and_credentials_advice(self):
        for transport in ("api", "cgi"):
            for status in (401, 403):
                with self.subTest(transport=transport, status=status):
                    response = Mock(status=status)
                    session = Mock(get=AsyncMock(return_value=response))
                    client = IpxCommandClient("192.0.2.1", "SECRET", session=session)
                    entity, _ = make_entity(RelaySwitch)
                    entity.control = (
                        Relay(client, 1) if transport == "api" else XPWM(client, 1)
                    )
                    with self.assertRaises(HomeAssistantError) as caught:
                        await entity.async_turn_off()
                    message = str(caught.exception)
                    for text in (
                        "Cannot turn off",
                        entity.entity_id,
                        f"HTTP {status}",
                        "credentials",
                        "attempts: 1, retries: 0",
                    ):
                        self.assertIn(text, message)
                    self.assertNotIn("Cannot confirm", message)
                    self.assertNotIn("SECRET", message)
                    session.get.assert_awaited_once()
                    response.close.assert_called_once()

    async def test_unload_error_has_entity_and_operation(self):
        entity, write = make_entity(RelaySwitch)
        entity.coordinator.commands.shutdown()
        with self.assertRaisesRegex(
            HomeAssistantError, "turn off.*switch.test_ipx.*unloading"
        ):
            await entity.async_turn_off()
        write.assert_not_awaited()

    async def test_global_budget_bounds_all_rgbw_writes(self):
        entity, write = make_entity(XPWMRGBWLight)
        calls = 0

        async def slow_write(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                await asyncio.sleep(0.03)
            else:
                await asyncio.Event().wait()

        write.side_effect = slow_write
        with (
            patch("custom_components.ipx800v4.commands.COMMAND_TIMEOUT", 0.06),
            self.assertRaisesRegex(
                HomeAssistantError, "turn off.*switch.test_ipx.*time budget"
            ),
        ):
            await asyncio.wait_for(entity.async_turn_off(), 0.5)
        self.assertEqual(calls, 2)
        entity.coordinator.async_request_refresh.assert_not_awaited()
        # Timeout released the locks and did not poison subsequent operations.
        write.side_effect = None
        await entity.async_turn_off()
        self.assertEqual(write.await_count, 6)

    async def test_global_budget_includes_backoff(self):
        entity, write = make_entity(RelaySwitch, TimeoutError())
        with (
            patch("custom_components.ipx800v4.commands.COMMAND_TIMEOUT", 0.02),
            self.assertRaisesRegex(HomeAssistantError, "time budget"),
        ):
            await asyncio.wait_for(entity.async_turn_off(), 0.5)
        write.assert_awaited_once()

    async def test_global_budget_includes_lock_wait_without_sending(self):
        entity, write = make_entity(RelaySwitch)
        lock = entity.coordinator.commands._locks.setdefault("R1", asyncio.Lock())
        async with lock:
            with (
                patch("custom_components.ipx800v4.commands.COMMAND_TIMEOUT", 0.02),
                self.assertRaisesRegex(HomeAssistantError, "time budget"),
            ):
                await asyncio.wait_for(entity.async_turn_off(), 0.5)
        write.assert_not_awaited()

    async def test_global_budget_closes_inflight_response(self):
        async def stalled_body():
            await asyncio.Event().wait()

        response = Mock(status=200, json=stalled_body)
        session = Mock(get=AsyncMock(return_value=response))
        client = IpxCommandClient("192.0.2.1", "SECRET", session=session)
        entity, _ = make_entity(RelaySwitch)
        entity.control = Relay(client, 1)
        with (
            patch("custom_components.ipx800v4.commands.COMMAND_TIMEOUT", 0.02),
            self.assertRaisesRegex(HomeAssistantError, "time budget"),
        ):
            await asyncio.wait_for(entity.async_turn_off(), 0.5)
        session.get.assert_awaited_once()
        response.close.assert_called_once()

    async def test_cover_tracking_starts_before_retry_and_only_once(self):
        entity, write = make_entity(X4VRCover)
        write.side_effect = [TimeoutError(), None]

        async def backoff(delay):
            entity.coordinator.async_track_cover_movement.assert_called_once_with(20)

        with patch(
            "custom_components.ipx800v4.commands.asyncio.sleep", side_effect=backoff
        ):
            await entity.async_open_cover()
        entity.coordinator.async_track_cover_movement.assert_called_once_with(20)
        self.assertEqual(write.await_count, 2)

    async def test_generic_cgi_error_and_missing_response_are_retried(self):
        for body, attempts in (("Error", 3), ("", 3)):
            with self.subTest(body=body):
                response = Mock(status=200, text=AsyncMock(return_value=body))
                session = Mock(get=AsyncMock(return_value=response))
                client = IpxCommandClient("192.0.2.1", "SECRET", session=session)
                entity, _ = make_entity(RelaySwitch)
                entity.control = XPWM(client, 1)
                with (
                    patch(
                        "custom_components.ipx800v4.commands.asyncio.sleep",
                        new_callable=AsyncMock,
                    ) as sleep,
                    self.assertRaises(HomeAssistantError),
                ):
                    await entity.async_turn_off()
                self.assertEqual(session.get.await_count, attempts)
                self.assertEqual(sleep.await_count, attempts - 1)

    async def test_cover_generic_error_then_success_keeps_one_tracking_request(self):
        entity, write = make_entity(X4VRCover)
        write.side_effect = [Ipx800RequestError(), None]

        async def backoff(delay):
            entity.coordinator.async_track_cover_movement.assert_called_once_with(20)

        with patch(
            "custom_components.ipx800v4.commands.asyncio.sleep", side_effect=backoff
        ):
            await entity.async_open_cover()
        self.assertEqual(write.await_count, 2)
        entity.coordinator.async_track_cover_movement.assert_called_once_with(20)
