"""Command failures reach callers without retries or fabricated state changes."""

import asyncio
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import test_coordinator
from homeassistant.components.climate import PRESET_ECO, HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pypx800 import (
    IPX800,
    XPWM,
    Ipx800CannotConnectError,
    Ipx800InvalidAuthError,
    Ipx800RequestError,
    Relay,
)

from custom_components.ipx800v4 import async_setup_entry
from custom_components.ipx800v4.climate import RelayClimate, X4FPClimate
from custom_components.ipx800v4.cover import X4VRCover
from custom_components.ipx800v4.light import (
    RelayLight,
    XDimmerLight,
    XPWMLight,
    XPWMRGBLight,
    XPWMRGBWLight,
)
from custom_components.ipx800v4.number import CounterNumber, VirtualAnalogInNumber
from custom_components.ipx800v4.switch import (
    RelaySwitch,
    VirtualInSwitch,
    VirtualOutSwitch,
)

CASES = (
    [
        (cls, f"async_{operation}", {})
        for cls in (
            RelaySwitch,
            VirtualInSwitch,
            VirtualOutSwitch,
            RelayLight,
            XDimmerLight,
            XPWMLight,
        )
        for operation in ("turn_on", "turn_off", "toggle")
    ]
    + [
        (cls, method, kwargs)
        for cls in (XPWMRGBLight, XPWMRGBWLight)
        for method, kwargs in (
            ("async_turn_on", {"brightness": 100}),
            ("async_turn_off", {}),
        )
    ]
    + [
        (X4VRCover, f"async_{operation}", {"position": 50})
        for operation in (
            "open_cover",
            "close_cover",
            "stop_cover",
            "set_cover_position",
            "open_cover_tilt",
            "close_cover_tilt",
        )
    ]
    + [
        (cls, method, kwargs)
        for cls in (X4FPClimate, RelayClimate)
        for method, kwargs in (
            ("async_set_hvac_mode", {"hvac_mode": HVACMode.HEAT}),
            ("async_set_preset_mode", {"preset_mode": PRESET_ECO}),
        )
    ]
    + [
        (cls, "async_set_native_value", {"value": 12})
        for cls in (CounterNumber, VirtualAnalogInNumber)
    ]
)


def make_entity(cls, error=None):
    """Keep platform methods and state readers real, replacing only I/O."""
    entity = cls.__new__(cls)
    entity.entity_id = "switch.test_ipx"
    entity._id = entity._ext_id = 1
    entity._ids = [1, 2, 3, 4]
    entity._transition = 0
    entity._default_brightness = 100
    entity.coordinator = SimpleNamespace(
        data={
            "R1": 1,
            "R2": 0,
            "VI1": 1,
            "VO1": 1,
            "PWM1": 25,
            "PWM2": 50,
            "PWM3": 75,
            "PWM4": 100,
            "G1": {"Etat": "ON", "Valeur": 50},
            "VR1-1": 50,
            "FP1 Zone 1": "Comfort",
            "C1": 12,
            "VA1": 12,
        },
        async_request_refresh=AsyncMock(),
    )
    controls = ["control", "control_minus", "control_plus"] + [
        f"xpwm_{mode}_{channel}" for mode in ("rgb", "rgbw") for channel in "rgbw"
    ]
    write = AsyncMock(side_effect=error)
    for name in controls:
        setattr(
            entity,
            name,
            SimpleNamespace(
                **{
                    method: write
                    for method in (
                        "on",
                        "off",
                        "toggle",
                        "set_level",
                        "set_mode",
                        "stop",
                        "set_pulse_up",
                        "set_pulse_down",
                        "set_value",
                    )
                }
            ),
        )
    entity.async_refresh_cover_state = AsyncMock()
    return entity, write


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_expected_errors_across_all_platform_commands(self):
        for cls, method, kwargs in CASES:
            for error_type in (
                Ipx800RequestError,
                Ipx800CannotConnectError,
                Ipx800InvalidAuthError,
                TimeoutError,
            ):
                with self.subTest(cls=cls.__name__, method=method, error=error_type):
                    error = error_type("http://secret:password@ipx/?key=SECRET")
                    entity, write = make_entity(cls, error)
                    before = deepcopy(entity.coordinator.data)
                    with (
                        self.assertNoLogs("custom_components.ipx800v4", "ERROR"),
                        self.assertRaises(HomeAssistantError) as raised,
                    ):
                        await getattr(entity, method)(**kwargs)
                    self.assertIs(raised.exception.__cause__, error)
                    self.assertIn(entity.entity_id, str(raised.exception))
                    self.assertNotIn("SECRET", str(raised.exception))
                    self.assertNotIn("password", str(raised.exception))
                    write.assert_awaited_once()
                    entity.coordinator.async_request_refresh.assert_not_awaited()
                    entity.async_refresh_cover_state.assert_not_called()
                    self.assertEqual(before, entity.coordinator.data)

    async def test_successful_commands_keep_refresh_behavior(self):
        for cls, method, kwargs in CASES:
            with self.subTest(cls=cls.__name__, method=method):
                entity, write = make_entity(cls)
                await getattr(entity, method)(**kwargs)
                await asyncio.sleep(0)
                self.assertGreater(write.await_count, 0)
                if cls is X4VRCover and method != "async_stop_cover":
                    entity.async_refresh_cover_state.assert_awaited_once()
                elif cls not in (CounterNumber, VirtualAnalogInNumber):
                    entity.coordinator.async_request_refresh.assert_awaited_once()

    async def test_multi_write_order_and_stop_after_partial_success(self):
        for cls, method, kwargs, names in (
            (
                RelayClimate,
                "async_set_preset_mode",
                {"preset_mode": PRESET_ECO},
                ["control_minus", "control_plus"],
            ),
            (
                XPWMRGBLight,
                "async_turn_on",
                {"rgb_color": (255, 128, 64)},
                ["xpwm_rgb_r", "xpwm_rgb_g", "xpwm_rgb_b"],
            ),
            (
                XPWMRGBWLight,
                "async_turn_off",
                {},
                ["xpwm_rgbw_w", "xpwm_rgbw_r", "xpwm_rgbw_g", "xpwm_rgbw_b"],
            ),
        ):
            with self.subTest(cls=cls.__name__):
                entity, _ = make_entity(cls)
                calls = []

                def writer(name, calls=calls, failed_name=names[1]):
                    async def write(*args):
                        calls.append(name)
                        if name == failed_name:
                            raise Ipx800RequestError()

                    return write

                for name in names:
                    setattr(
                        entity,
                        name,
                        SimpleNamespace(
                            **{op: writer(name) for op in ("on", "off", "set_level")}
                        ),
                    )
                with self.assertRaises(HomeAssistantError):
                    await getattr(entity, method)(**kwargs)
                await asyncio.sleep(0)
                self.assertEqual(calls, names[:2])
                entity.coordinator.async_request_refresh.assert_not_awaited()

    async def test_programming_errors_and_cancellation_are_not_disguised(self):
        for error in (ValueError("bug"), asyncio.CancelledError()):
            entity, write = make_entity(RelaySwitch, error)
            with self.assertRaises(type(error)) as raised:
                await entity.async_toggle()
            self.assertIs(raised.exception, error)
            write.assert_awaited_once()

    async def test_error_reaches_blocking_home_assistant_service_call(self):
        hass = HomeAssistant(".")
        entity, _ = make_entity(RelaySwitch, Ipx800CannotConnectError())

        async def handler(call):
            await entity.async_toggle()

        hass.services.async_register("ipx800v4", "test_toggle", handler)
        with self.assertRaises(HomeAssistantError):
            await hass.services.async_call("ipx800v4", "test_toggle", blocking=True)

    async def test_setup_separates_single_attempt_writes_from_reads(self):
        session = Mock()
        entry = Mock(
            data={
                "host": "192.0.2.1",
                "port": 80,
                "api_key": "SECRET",
                "name": "IPX",
                "devices": [],
            },
            options={},
            entry_id="test",
        )
        hass = SimpleNamespace(
            data={},
            config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock()),
        )
        coordinator = Mock(async_config_entry_first_refresh=AsyncMock())
        with (
            patch(
                "custom_components.ipx800v4.async_get_clientsession",
                return_value=session,
            ),
            patch("custom_components.ipx800v4.dr.async_get", return_value=Mock()),
            patch(
                "custom_components.ipx800v4.IpxDataUpdateCoordinator",
                return_value=coordinator,
            ),
            patch("custom_components.ipx800v4.Debouncer"),
            patch("custom_components.ipx800v4.IPX800", wraps=IPX800) as factory,
        ):
            await async_setup_entry(hass, entry)
        self.assertNotIn("request_retries", factory.call_args_list[0].kwargs)
        self.assertEqual(factory.call_args_list[1].kwargs["request_retries"], 1)
        client = hass.data["ipx800v4"]["test"]["controller"]
        # Use real pypx800 API and CGI write paths with unsuccessful responses.
        for control, command in (
            (Relay(client, 1), "toggle"),
            (XPWM(client, 1), "off"),
        ):
            session.get = AsyncMock(
                return_value=Mock(
                    status=200,
                    json=AsyncMock(return_value={"status": "Error"}),
                    text=AsyncMock(return_value="Error"),
                )
            )
            with patch("pypx800.ipx800.sleep"), self.assertRaises(Ipx800RequestError):
                await getattr(control, command)()
            session.get.assert_awaited_once()


class CommandReadRecoveryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_coordinator.ReadRecoveryTests.asyncSetUp
    asyncTearDown = test_coordinator.ReadRecoveryTests.asyncTearDown
    make_coordinator = test_coordinator.ReadRecoveryTests.make_coordinator
    assert_next_read = test_coordinator.ReadRecoveryTests.assert_next_read

    async def test_successful_write_then_failed_pull_only_retries_reads(self):
        coordinator, reader = self.make_coordinator()
        await coordinator.async_config_entry_first_refresh()
        coordinator.async_add_listener(Mock())
        timestamp = coordinator.last_successful_read
        entity, write = make_entity(RelaySwitch)
        entity.coordinator = coordinator
        reader.side_effect = Ipx800CannotConnectError()
        await coordinator.async_refresh()
        failures = coordinator.consecutive_failures
        await entity.async_toggle()
        self.assertEqual(coordinator.consecutive_failures, failures)
        await asyncio.sleep(0.6)
        write.assert_awaited_once()
        self.assertEqual(coordinator.consecutive_failures, failures + 1)
        self.assertEqual(coordinator.last_successful_read, timestamp)
        self.assertEqual(coordinator.data["R1"], 1)
        self.assert_next_read(coordinator, 15)
