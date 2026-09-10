"""Coordinate reads and tolerate a bounded number of communication failures."""

from datetime import datetime
import logging

from aiohttp import ClientResponseError, InvalidURL
from pypx800 import (
    Ipx800CannotConnectError,
    Ipx800InvalidAuthError,
    Ipx800RequestError,
)

from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import MAX_READ_FAILURES, MAX_READ_RETRY_DELAY

_LOGGER = logging.getLogger(__name__)


class IpxTransientReadError(UpdateFailed):
    """A communication failure, with an optional bounded recovery delay."""


class IpxDataUpdateCoordinator(DataUpdateCoordinator):
    """Keep acquisition status separate from temporary cached availability.

    UpdateFailed.retry_after uses Home Assistant's existing polling timer and
    refresh lock. Push/manual reads therefore replace a pending retry, and a
    success or the third failure automatically restores the configured interval.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize per-controller recovery state."""
        super().__init__(*args, **kwargs)
        self.consecutive_failures = 0
        self.last_successful_read: datetime | None = None
        self._retain_data = False

    @property
    def data_available(self) -> bool:
        """Return whether a successful snapshot is still usable by entities."""
        return self.data is not None and (
            self.last_update_success or self._retain_data
        )

    @callback
    def _schedule_refresh(self) -> None:
        """Do not reschedule a read that finishes while the entry is unloading."""
        if not self._shutdown_requested:
            super()._schedule_refresh()

    async def _async_update_data(self) -> dict:
        """Read once; never present cached data as a successful acquisition."""
        was_available = self.data_available
        self._retain_data = False
        try:
            data = await super()._async_update_data()
        except Ipx800InvalidAuthError as err:
            raise ConfigEntryAuthFailed("IPX800 authentication failed") from err
        except Ipx800RequestError as err:
            raise ConfigEntryError("IPX800 rejected the API request") from err
        except (Ipx800CannotConnectError, TimeoutError) as err:
            # pypx800 wraps aiohttp errors. Do not soften definitive HTTP or
            # URL errors, and never include exception URLs (containing API keys).
            cause = err.__cause__
            if isinstance(cause, InvalidURL):
                raise ConfigEntryError("Invalid IPX800 URL") from err
            if isinstance(cause, ClientResponseError):
                if cause.status in (401, 403):
                    raise ConfigEntryAuthFailed("IPX800 authentication failed") from err
                if 400 <= cause.status < 500 and cause.status not in (408, 429):
                    raise ConfigEntryError("IPX800 rejected the HTTP request") from err

            self.consecutive_failures += 1
            self._retain_data = (
                was_available and self.consecutive_failures < MAX_READ_FAILURES
            )
            retry_delay = (
                min(self.update_interval.total_seconds(), MAX_READ_RETRY_DELAY)
                if self._retain_data
                else None
            )
            _LOGGER.debug(
                "%s: read failed (%s), consecutive failures=%s, "
                "last successful read=%s, next read in %ss",
                self.name,
                type(err).__name__,
                self.consecutive_failures,
                self.last_successful_read,
                retry_delay
                if retry_delay is not None
                else self.update_interval.total_seconds(),
            )
            raise IpxTransientReadError(
                "IPX800 communication failed", retry_after=retry_delay
            ) from err

        self.consecutive_failures = 0
        self.last_successful_read = dt_util.utcnow()
        return data

    async def _async_refresh(self, *, log_failures=True, **kwargs) -> None:
        """Publish the availability threshold while retaining real read failures."""
        was_available = self.data_available
        previous_update_success = self.last_update_success
        # Handle expected failure logging below: HA otherwise logs an error on
        # the first transient failure. Unexpected exceptions still get a traceback.
        await super()._async_refresh(log_failures=False, **kwargs)

        if log_failures and not self.last_update_success:
            if isinstance(self.last_exception, IpxTransientReadError):
                if was_available and not self.data_available:
                    _LOGGER.warning(
                        "%s: unavailable after %s consecutive failed reads; "
                        "last successful read=%s, next read in %ss",
                        self.name,
                        self.consecutive_failures,
                        self.last_successful_read,
                        self.update_interval.total_seconds(),
                    )
            elif (previous_update_success or was_available) and isinstance(
                self.last_exception, (ConfigEntryAuthFailed, ConfigEntryError)
            ):
                _LOGGER.error(
                    "%s: read failed (%s); last successful read=%s",
                    self.name,
                    type(self.last_exception).__name__,
                    self.last_successful_read,
                )

        # HA skips listeners on consecutive failed acquisitions. The third
        # failure must still publish the change from retained data to unavailable.
        if (
            not previous_update_success
            and not self.last_update_success
            and was_available != self.data_available
        ):
            self.async_update_listeners()
