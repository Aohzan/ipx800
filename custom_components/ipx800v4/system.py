"""Read controller diagnostics from the IPX800 V4 XML interface."""

from datetime import datetime, timedelta
import logging
import re
from xml.etree import ElementTree

from aiohttp import BasicAuth, ClientError, ClientSession, ClientTimeout

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)
CLOCK_TOLERANCE = 60


class IpxSystemData:
    """Fetch one system snapshot per coordinator refresh."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
    ) -> None:
        self._session = session
        self._url = f"http://{host}:{port}/user/status.xml"
        self._auth = BasicAuth(username, password or "") if username else None
        self._last_boot: datetime | None = None
        self._last_uptime: int | None = None
        self._failed = False

    async def async_get(self) -> dict:
        """Read diagnostics without making I/O entities unavailable on failure."""
        try:
            async with self._session.get(
                self._url, auth=self._auth, timeout=ClientTimeout(total=5)
            ) as response:
                response.raise_for_status()
                root = ElementTree.fromstring(await response.text())
            if root.tag != "response":
                raise ValueError("Expected an IPX800 XML response")
        except (ClientError, TimeoutError, ElementTree.ParseError, ValueError) as err:
            if not self._failed:
                _LOGGER.warning(
                    "Cannot read IPX800 system diagnostics from %s: %s. "
                    "Check YAML username/password if the web interface is protected",
                    self._url,
                    err,
                )
            self._failed = True
            return {}
        self._failed = False

        now = dt_util.utcnow()
        data = {}
        # GCE: wuc0 is seconds since boot; lps0 is loops per second, not CPU %.
        for tag, key in (("wuc0", "uptime"), ("lps0", "load")):
            value = root.findtext(tag, "").strip()
            if value.isascii() and value.isdecimal() and len(value) <= 10:
                data[key] = int(value)

        if (uptime := data.get("uptime")) is not None:
            estimated_boot = now - timedelta(seconds=uptime)
            # Keep the timestamp stable across polling jitter, but detect a reset
            # even when a reboot was missed between two widely spaced polls.
            if (
                self._last_boot is None
                or (self._last_uptime is not None and uptime < self._last_uptime)
                or abs((estimated_boot - self._last_boot).total_seconds()) > 5
            ):
                self._last_boot = estimated_boot.replace(microsecond=0)
            self._last_uptime = uptime
            data["last_boot"] = self._last_boot

        date = root.findtext("date", "").strip()
        time = root.findtext("heure", "").strip()
        for date_format in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                ipx_time = datetime.strptime(
                    f"{date} {time}", f"{date_format} %H:%M:%S"
                )
            except ValueError:
                continue
            # XML has no UTC offset: compare to HA's configured local time.
            local_now = dt_util.as_local(now).replace(tzinfo=None)
            data["clock_offset"] = round((ipx_time - local_now).total_seconds())
            data["clock_in_sync"] = abs(data["clock_offset"]) <= CLOCK_TOLERANCE
            break

        mac = root.findtext("mac", "").strip()
        if re.fullmatch(r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}", mac):
            data["mac"] = mac.lower()
        return data
