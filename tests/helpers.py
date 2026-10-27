"""Helpers shared by the regression tests written with unittest."""

# Regression tests written with unittest, run by pytest
# ruff: noqa: D102, PT009, PT027

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.ipx800v4.commands import CommandManager
from custom_components.ipx800v4.coordinator import IpxDataUpdateCoordinator
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.debounce import Debouncer

STRINGS = json.loads(
    (
        Path(__file__).parent.parent / "custom_components/ipx800v4/strings.json"
    ).read_text(encoding="utf-8")
)


def error_message(err: HomeAssistantError) -> str:
    """Return the English message of a translated error, as shown to the user."""
    template = STRINGS["exceptions"][err.translation_key]["message"]
    return template.format(**(err.translation_placeholders or {}))


@contextmanager
def assert_raises_message(
    test: unittest.TestCase, pattern: str
) -> Iterator[unittest.case._AssertRaisesContext]:
    """Assert a translated error is raised with a message matching the pattern."""
    with test.assertRaises(HomeAssistantError) as raised:
        yield raised
    test.assertRegex(error_message(raised.exception), pattern)


class CoordinatorTestCase(unittest.IsolatedAsyncioTestCase):
    """Exercise HA's polling timer, debounce and listener handling."""

    async def asyncSetUp(self):
        self.coordinators = []
        self.tasks = []
        # Each successful read deletes the authentication repair issue, the
        # fake hass has no issue registry.
        patcher = patch("custom_components.ipx800v4.coordinator.ir.async_delete_issue")
        patcher.start()
        self.addCleanup(patcher.stop)

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
        entry.async_create_background_task.side_effect = lambda hass, coro, **kwargs: (
            create_task(coro)
        )
        reader = AsyncMock(return_value={"R1": 1, "system": {"load": 10}})
        logger = logging.getLogger("ipx800_test")
        coordinator = IpxDataUpdateCoordinator(
            hass,
            logger,
            name=f"Test IPX {len(self.coordinators)} (192.0.2.1)",
            config_entry=entry,
            controller_device_id="controller",
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


def make_entity(cls, error=None):
    """Keep platform methods and state readers real, replacing only I/O."""
    entity = cls.__new__(cls)
    entity.entity_id = "switch.test_ipx"
    entity._id = entity._ext_id = 1
    entity._ids = [1, 2, 3, 4]
    entity._retry_commands = True
    entity._transition = 0
    entity._default_brightness = 100
    entity.coordinator = SimpleNamespace(
        commands=CommandManager(),
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
            "ENO ACTIONNEUR1": 1,
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
                **dict.fromkeys(
                    (
                        "on",
                        "off",
                        "toggle",
                        "set_level",
                        "set_mode",
                        "stop",
                        "set_pulse_up",
                        "set_pulse_down",
                        "set_value",
                    ),
                    write,
                )
            ),
        )
    entity.coordinator.async_track_cover_movement = Mock()
    return entity, write
