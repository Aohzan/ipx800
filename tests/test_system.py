"""Exercise real XML parsing and diagnostics request failure handling."""

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from aiohttp import BasicAuth, ClientConnectionError, ClientResponseError

from custom_components.ipx800v4.system import IpxSystemData

NOW = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
LOGGER = "custom_components.ipx800v4.system"


class SystemDataTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.response = Mock()
        self.response.text = AsyncMock(return_value="<response />")
        context = AsyncMock()
        context.__aenter__.return_value = self.response
        self.session = Mock()
        self.session.get.return_value = context
        self.reader = IpxSystemData(self.session, "192.0.2.1", 8080, None, None)
        self.now = patch(f"{LOGGER}.dt_util.utcnow", return_value=NOW).start()
        self.addCleanup(patch.stopall)

    async def read_xml(self, xml):
        self.response.text.return_value = xml
        return await self.reader.async_get()

    async def test_complete_snapshot_and_request(self):
        with patch(f"{LOGGER}.dt_util.as_local", return_value=NOW):
            data = await self.read_xml(
                "<response><wuc0>3600</wuc0><lps0>1234</lps0>"
                "<date>10/09/2026</date><heure>12:00:00</heure>"
                "<mac>AA:BB:CC:DD:EE:FF</mac></response>"
            )
        self.assertEqual(data, {
            "uptime": 3600, "load": 1234,
            "last_boot": NOW - timedelta(hours=1),
            "clock_offset": 0, "clock_in_sync": True,
            "mac": "aa:bb:cc:dd:ee:ff",
        })
        args, kwargs = self.session.get.call_args
        self.assertEqual(args, ("http://192.0.2.1:8080/user/status.xml",))
        self.assertIsNone(kwargs["auth"])
        self.assertEqual(kwargs["timeout"].total, 5)
        self.response.raise_for_status.assert_called_once()

    async def test_partial_snapshot_does_not_reuse_missing_fields(self):
        await self.read_xml("<response><wuc0>10</wuc0><lps0>20</lps0></response>")
        self.assertEqual(await self.read_xml("<response><lps0>30</lps0></response>"), {"load": 30})
        self.assertEqual(await self.read_xml("<response />"), {})

    async def test_invalid_numeric_clock_and_mac_fields_are_ignored(self):
        for value in ("-1", "1.5", "NaN", "١٢", "12345678901", ""):
            with self.subTest(value=value):
                self.assertEqual(await self.read_xml(
                    f"<response><wuc0>{value}</wuc0><lps0>{value}</lps0>"
                    "<date>31/02/2026</date><heure>25:00:00</heure>"
                    "<mac>AA:BB:CC:DD:EE:GG</mac></response>"
                ), {})
        data = await self.read_xml("<response><wuc0> 0 </wuc0><lps0> 42 </lps0></response>")
        self.assertEqual(data, {"uptime": 0, "last_boot": NOW, "load": 42})

    async def test_boot_time_stability_and_reboot_detection(self):
        first = await self.read_xml("<response><wuc0>100</wuc0></response>")
        self.now.return_value = NOW + timedelta(seconds=12)
        jitter = await self.read_xml("<response><wuc0>110</wuc0></response>")
        self.assertEqual(jitter["last_boot"], first["last_boot"])
        self.now.return_value = NOW + timedelta(seconds=20)
        reboot = await self.read_xml("<response><wuc0>5</wuc0></response>")
        self.assertEqual(reboot["last_boot"], NOW + timedelta(seconds=15))
        # Reboot between widely spaced polls, with uptime already above 5.
        self.now.return_value = NOW + timedelta(seconds=300)
        missed = await self.read_xml("<response><wuc0>20</wuc0></response>")
        self.assertEqual(missed["last_boot"], NOW + timedelta(seconds=280))

    async def test_clock_formats_local_timezone_and_tolerance(self):
        local = NOW.astimezone(ZoneInfo("Europe/Paris"))
        with patch(f"{LOGGER}.dt_util.as_local", return_value=local):
            for date_format in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
                for offset in (-61, -60, 0, 60, 61):
                    with self.subTest(date_format=date_format, offset=offset):
                        clock = local + timedelta(seconds=offset)
                        data = await self.read_xml(
                            f"<response><date>{clock.strftime(date_format)}</date>"
                            f"<heure>{clock:%H:%M:%S}</heure></response>"
                        )
                        self.assertEqual(data["clock_offset"], offset)
                        self.assertEqual(data["clock_in_sync"], abs(offset) <= 60)

    async def test_malformed_xml_and_wrong_root_allow_recovery(self):
        with self.assertLogs(LOGGER, level="WARNING"):
            for xml in ("<response>", "<html>login</html>"):
                self.assertEqual(await self.read_xml(xml), {})
        self.assertEqual(await self.read_xml("<response><lps0>42</lps0></response>"), {"load": 42})

    async def test_network_timeout_and_http_errors_return_empty_snapshot(self):
        for error in (
            ClientConnectionError("connection failed"),
            TimeoutError(),
            ClientResponseError(Mock(real_url="http://192.0.2.1"), (), status=401),
            ClientResponseError(Mock(real_url="http://192.0.2.1"), (), status=500),
        ):
            with self.subTest(error=type(error).__name__):
                self.reader = IpxSystemData(self.session, "192.0.2.1", 80, None, None)
                self.response.raise_for_status.side_effect = error
                with self.assertLogs(LOGGER, level="WARNING"):
                    self.assertEqual(await self.reader.async_get(), {})
                self.response.raise_for_status.side_effect = None
                self.assertEqual(await self.read_xml("<response><lps0>42</lps0></response>"), {"load": 42})

    async def test_five_consecutive_failures_stop_requests_without_credentials(self):
        self.session.get.side_effect = ClientConnectionError("offline")
        with self.assertLogs(LOGGER, level="WARNING"):
            for _ in range(8):
                self.assertEqual(await self.reader.async_get(), {})
        self.assertEqual(self.session.get.call_count, 5)

    async def test_success_resets_failure_budget(self):
        with self.assertLogs(LOGGER, level="WARNING"):
            for _ in range(4):
                await self.read_xml("invalid XML")
        await self.read_xml("<response><lps0>42</lps0></response>")
        with self.assertLogs(LOGGER, level="WARNING"):
            for _ in range(6):
                await self.read_xml("invalid XML")
        self.assertEqual(self.session.get.call_count, 10)

    async def test_credentials_are_sent_and_failures_do_not_disable_polling(self):
        for password in (None, "secret"):
            with self.subTest(password=password):
                self.reader = IpxSystemData(self.session, "192.0.2.1", 80, "admin", password)
                self.session.get.reset_mock()
                with self.assertLogs(LOGGER, level="WARNING"):
                    for _ in range(7):
                        await self.read_xml("invalid XML")
                self.assertEqual(self.session.get.call_count, 7)
                self.assertEqual(self.session.get.call_args.kwargs["auth"], BasicAuth("admin", password or ""))
                self.assertEqual(await self.read_xml("<response><lps0>42</lps0></response>"), {"load": 42})
