"""Exercise retry transport, fixed targets and competing command intents."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

from aiohttp import ClientResponseError, InvalidURL
from homeassistant.exceptions import HomeAssistantError
from pypx800 import (
    X4VR,
    XPWM,
    Ipx800CannotConnectError,
    Ipx800InvalidAuthError,
    Ipx800RequestError,
)
from test_commands import make_entity

from custom_components.ipx800v4.commands import IpxCommandClient
from custom_components.ipx800v4.cover import X4VRCover
from custom_components.ipx800v4.light import RelayLight, XPWMRGBLight
from custom_components.ipx800v4.switch import RelaySwitch


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_failure_then_success_uses_fixed_target(self):
        entity, write = make_entity(RelaySwitch)
        write.side_effect = [Ipx800CannotConnectError(), TimeoutError(), None]
        with patch(
            "custom_components.ipx800v4.commands.asyncio.sleep", new_callable=AsyncMock
        ) as sleep:
            await entity.async_turn_on()
        self.assertEqual(write.await_count, 3)
        self.assertEqual(sleep.await_args_list, [call(1), call(2)])
        entity.coordinator.async_request_refresh.assert_awaited_once()

    async def test_only_failed_rgb_channel_retried_with_frozen_value(self):
        entity, _ = make_entity(XPWMRGBLight)
        red, green, blue = AsyncMock(), AsyncMock(), AsyncMock()
        green.side_effect = [TimeoutError(), None]
        entity.xpwm_rgb_r.set_level = red
        entity.xpwm_rgb_g.set_level = green
        entity.xpwm_rgb_b.set_level = blue

        async def update_state(delay):
            entity.coordinator.data.clear()

        with patch(
            "custom_components.ipx800v4.commands.asyncio.sleep",
            side_effect=update_state,
        ):
            await entity.async_turn_on(brightness=128)
        red.assert_awaited_once_with(17, 0)
        self.assertEqual(green.await_args_list, [call(34, 0), call(34, 0)])
        blue.assert_awaited_once_with(50, 0)

    async def test_definitive_http_and_url_errors_not_retried(self):
        for cause in [
            InvalidURL("bad"),
            *[
                ClientResponseError(Mock(), (), status=status)
                for status in (400, 401, 403, 404)
            ],
        ]:
            entity, write = make_entity(RelaySwitch)
            error = Ipx800CannotConnectError()
            error.__cause__ = cause
            write.side_effect = error
            with (
                patch(
                    "custom_components.ipx800v4.commands.asyncio.sleep",
                    new_callable=AsyncMock,
                ) as sleep,
                self.assertRaises(HomeAssistantError),
            ):
                await entity.async_turn_on()
            write.assert_awaited_once()
            sleep.assert_not_awaited()

    async def test_new_stop_runs_during_backoff_and_prevents_stale_retry(self):
        entity, _ = make_entity(X4VRCover)
        started, resume = asyncio.Event(), asyncio.Event()
        opening = AsyncMock(side_effect=TimeoutError())
        stop = AsyncMock()
        entity.control.on, entity.control.stop = opening, stop

        async def backoff(delay):
            started.set()
            await resume.wait()

        with patch(
            "custom_components.ipx800v4.commands.asyncio.sleep", side_effect=backoff
        ):
            task = asyncio.create_task(entity.async_open_cover())
            await asyncio.wait_for(started.wait(), 1)
            await asyncio.wait_for(entity.async_stop_cover(), 1)
            stop.assert_awaited_once()
            resume.set()
            with self.assertRaisesRegex(HomeAssistantError, "superseded"):
                await task
        opening.assert_awaited_once()

    async def test_aliases_share_ordering_during_inflight_write(self):
        first, _ = make_entity(RelaySwitch)
        second, _ = make_entity(RelayLight)
        second.coordinator = first.coordinator
        started, finish = asyncio.Event(), asyncio.Event()
        calls = []

        async def old_write():
            calls.append("on")
            started.set()
            await finish.wait()
            raise TimeoutError()

        async def new_write():
            calls.append("off")

        first.control.on = old_write
        second.control.off = new_write
        old = asyncio.create_task(first.async_turn_on())
        await started.wait()
        new = asyncio.create_task(second.async_turn_off())
        await asyncio.sleep(0)
        self.assertEqual(calls, ["on"])
        finish.set()
        with self.assertRaisesRegex(HomeAssistantError, "superseded"):
            await old
        await new
        self.assertEqual(calls, ["on", "off"])

    async def test_real_backoff_yields_and_cancellation_stops_retry(self):
        entity, write = make_entity(RelaySwitch, TimeoutError())
        task = asyncio.create_task(entity.async_turn_on())
        # A real one-second backoff must yield to other HA work immediately.
        await asyncio.sleep(0.01)
        self.assertFalse(task.done())
        write.assert_awaited_once()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        write.assert_awaited_once()

    async def test_unload_cancels_remaining_retries(self):
        entity, write = make_entity(RelaySwitch, TimeoutError())

        async def unload(delay):
            entity.coordinator.commands.shutdown()

        with (
            patch(
                "custom_components.ipx800v4.commands.asyncio.sleep", side_effect=unload
            ),
            self.assertRaisesRegex(HomeAssistantError, "unloading"),
        ):
            await entity.async_turn_on()
        write.assert_awaited_once()

    async def test_x4vr_wire_commands_replay_absolute_targets_only(self):
        for method, kwargs, params, attempts in (
            ("async_open_cover", {}, {"SetVR01": "0"}, 2),
            ("async_close_cover", {}, {"SetVR01": "100"}, 2),
            ("async_set_cover_position", {"position": 35}, {"SetVR01": "65"}, 2),
            ("async_stop_cover", {}, {"SetVR01": "101"}, 2),
            ("async_open_cover_tilt", {}, {"SetPulseUP01": "1"}, 1),
            ("async_close_cover_tilt", {}, {"SetPulseDOWN01": "1"}, 1),
        ):
            with self.subTest(method=method):
                entity, _ = make_entity(X4VRCover)
                client = SimpleNamespace(
                    request_api=AsyncMock(side_effect=[TimeoutError(), None])
                )
                entity.control = X4VR(client, 1, 1)
                with patch(
                    "custom_components.ipx800v4.commands.asyncio.sleep",
                    new_callable=AsyncMock,
                ):
                    if attempts == 1:
                        with self.assertRaises(HomeAssistantError):
                            await getattr(entity, method)(**kwargs)
                    else:
                        await getattr(entity, method)(**kwargs)
                await asyncio.sleep(0)
                self.assertEqual(
                    client.request_api.await_args_list, [call(params)] * attempts
                )

    async def test_cgi_error_never_calls_blocking_sleep(self):
        response = Mock(status=200, text=AsyncMock(return_value="Error"))
        session = Mock(get=AsyncMock(return_value=response))
        client = IpxCommandClient(
            "192.0.2.1", "SECRET", session=session, request_retries=1
        )
        with (
            patch("pypx800.ipx800.sleep", side_effect=AssertionError("blocking sleep")),
            self.assertRaises(Ipx800RequestError),
        ):
            await XPWM(client, 1).off()
        session.get.assert_awaited_once()
        response.close.assert_called_once()

    async def test_device_can_disable_replay_for_scenario_outputs(self):
        entity, write = make_entity(RelaySwitch, TimeoutError())
        entity._retry_commands = False
        with self.assertRaises(HomeAssistantError):
            await entity.async_turn_on()
        write.assert_awaited_once()

    async def test_cgi_body_timeout_closes_response(self):
        response = Mock(status=200, text=AsyncMock(side_effect=TimeoutError()))
        session = Mock(get=AsyncMock(return_value=response))
        client = IpxCommandClient(
            "192.0.2.1", "SECRET", session=session, request_retries=1
        )
        with self.assertRaises(Ipx800CannotConnectError):
            await client.request_cgi({"SetPWM": 1})
        response.close.assert_called_once()

    async def test_cgi_status_classification_and_success(self):
        for status in (200, 401, 403, 404, 503):
            with self.subTest(status=status):
                response = Mock(status=status, text=AsyncMock(return_value="Success"))
                if status >= 400:
                    response.raise_for_status.side_effect = ClientResponseError(
                        Mock(), (), status=status
                    )
                session = Mock(get=AsyncMock(return_value=response))
                client = IpxCommandClient(
                    "192.0.2.1", "SECRET", session=session, request_retries=1
                )
                if status == 200:
                    self.assertEqual(await client.request_cgi({"SetPWM": 1}), "Success")
                else:
                    expected = (
                        Ipx800InvalidAuthError
                        if status in (401, 403)
                        else Ipx800CannotConnectError
                    )
                    with self.assertRaises(expected):
                        await client.request_cgi({"SetPWM": 1})
                response.close.assert_called_once()
                session.get.assert_awaited_once()

    async def test_keyword_only_and_mixed_arguments_survive_retries(self):
        for args, kwargs in (
            ((42,), {"duration": 5, "enabled": True}),
            ((), {"value": 42, "duration": 5, "enabled": True}),
        ):
            with self.subTest(args=args):
                entity, _ = make_entity(RelaySwitch)
                received = []

                async def command(value, *, duration, enabled, received=received):
                    received.append((value, duration, enabled))
                    if len(received) < 3:
                        raise TimeoutError()

                with patch(
                    "custom_components.ipx800v4.commands.asyncio.sleep",
                    new_callable=AsyncMock,
                ):
                    async with entity._command_error("test named arguments"):
                        await entity._async_write(command, *args, retry=True, **kwargs)
                self.assertEqual(received, [(42, 5, True)] * 3)

    async def test_response_failures_report_actual_attempts_without_secrets(self):
        from json import JSONDecodeError

        from aiohttp import ContentTypeError

        for failure, cause, reason in (
            (Ipx800RequestError(), None, "response did not confirm success"),
            (
                Ipx800CannotConnectError(),
                ContentTypeError(Mock(), (), status=200, message="SECRET"),
                "unexpected response content type",
            ),
            (
                Ipx800RequestError(),
                JSONDecodeError("SECRET", "SECRET", 0),
                "invalid response content",
            ),
            (Ipx800CannotConnectError(), TimeoutError("SECRET"), "request timeout"),
            (TimeoutError("SECRET"), None, "request timeout"),
        ):
            failure.__cause__ = cause
            for enabled in (True, False):
                entity, write = make_entity(RelaySwitch, failure)
                entity._retry_commands = enabled
                with (
                    patch(
                        "custom_components.ipx800v4.commands.asyncio.sleep",
                        new_callable=AsyncMock,
                    ) as sleep,
                    self.assertRaises(HomeAssistantError) as raised,
                ):
                    await entity.async_turn_on()
                message = str(raised.exception)
                self.assertIn(reason, message)
                self.assertIn(
                    "attempts: 3, retries: 2" if enabled else "attempts: 1, retries: 0",
                    message,
                )
                self.assertNotIn("SECRET", message)
                self.assertEqual(write.await_count, 3 if enabled else 1)
                self.assertEqual(
                    sleep.await_args_list, [call(1), call(2)] if enabled else []
                )

    async def test_json_transport_retries_response_failures_but_not_http_refusal(self):
        from json import JSONDecodeError

        from aiohttp import ContentTypeError
        from pypx800 import Relay

        for status, body, error, attempts in (
            (200, {"status": "Error"}, None, 3),
            (200, [], None, 3),
            (200, None, ContentTypeError(Mock(), (), status=200), 3),
            (200, None, JSONDecodeError("invalid", "x", 0), 3),
            (200, None, TimeoutError(), 3),
            (401, None, None, 1),
            (403, None, None, 1),
            (404, None, None, 1),
            (503, None, None, 3),
        ):
            with self.subTest(status=status, error=type(error).__name__):
                response = Mock(
                    status=status, json=AsyncMock(return_value=body, side_effect=error)
                )
                if status >= 400:
                    response.raise_for_status.side_effect = ClientResponseError(
                        Mock(), (), status=status
                    )
                session = Mock(get=AsyncMock(return_value=response))
                client = IpxCommandClient(
                    "192.0.2.1", "SECRET", session=session, request_retries=1
                )
                entity, _ = make_entity(RelaySwitch)
                entity.control = Relay(client, 1)
                with (
                    patch(
                        "custom_components.ipx800v4.commands.asyncio.sleep",
                        new_callable=AsyncMock,
                    ),
                    self.assertRaises(HomeAssistantError) as raised,
                ):
                    await entity.async_turn_on()
                self.assertEqual(session.get.await_count, attempts)
                self.assertEqual(response.close.call_count, attempts)
                self.assertIn(
                    f"attempts: {attempts}, retries: {attempts - 1}",
                    str(raised.exception),
                )

    async def test_timeout_covers_entire_json_body_without_blocking_loop(self):
        from pypx800 import Relay

        async def stalled_body():
            await asyncio.Event().wait()

        response = Mock(status=200, json=stalled_body)
        session = Mock(get=AsyncMock(return_value=response))
        client = IpxCommandClient(
            "192.0.2.1",
            "SECRET",
            session=session,
            request_retries=1,
            request_timeout=0.01,
        )
        entity, _ = make_entity(RelaySwitch)
        entity.control = Relay(client, 1)
        with (
            patch("custom_components.ipx800v4.commands.RETRY_DELAYS", (0, 0)),
            self.assertRaisesRegex(HomeAssistantError, "request timeout.*attempts: 3"),
        ):
            await asyncio.wait_for(entity.async_turn_on(), 1)
        self.assertEqual(session.get.await_count, 3)
        self.assertEqual(response.close.call_count, 3)
