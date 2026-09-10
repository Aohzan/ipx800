"""Coordinate reads with bounded communication and missing-field recovery."""

import logging
from datetime import datetime
from math import isfinite
from time import monotonic

from aiohttp import ClientResponseError, InvalidURL
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pypx800 import (
    Ipx800CannotConnectError,
    Ipx800InvalidAuthError,
    Ipx800RequestError,
)

from .const import MAX_READ_FAILURES, MAX_READ_RETRY_DELAY

_LOGGER = logging.getLogger(__name__)


class IpxTransientReadError(UpdateFailed):
    """A communication failure, with an optional bounded recovery delay."""


class IpxDataUpdateCoordinator(DataUpdateCoordinator):
    """Keep acquisition status separate from temporary cached availability.

    UpdateFailed.retry_after uses Home Assistant's existing polling timer and
    refresh lock. Push/manual reads therefore replace a pending retry, and a
    completed recovery restores the configured interval. Missing-field recovery
    shares that timer; the freshness timer only publishes expired data.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize per-controller recovery state."""
        super().__init__(*args, **kwargs)
        self.consecutive_failures = 0
        self.last_successful_read: datetime | None = None
        self._retain_data = False
        self.push_entities = {}
        self.field_push_times: dict[str, float] = {}
        self._freshness_expiry = None
        self._required_fields: dict[str, int] = {}
        self.field_receipt_times: dict[str, float] = {}
        # First detected omission and number of incomplete successful reads.
        self._missing_fields: dict[str, tuple[float, int]] = {}
        self._last_read_time: float | None = None
        self._read_in_progress = False

    @property
    def recovery_delay(self) -> float:
        """Share the same bounded read interval for both recovery policies."""
        return min(self.update_interval.total_seconds(), MAX_READ_RETRY_DELAY)

    @staticmethod
    def _valid_field(key: str, value) -> bool:
        """Reject unusable API values without treating zero/off as absent."""
        if key.startswith("FP"):
            return isinstance(value, str) and bool(value)
        if key.startswith("G"):
            return (
                isinstance(value, dict)
                and value.get("Etat") in ("ON", "OFF")
                and isinstance(value.get("Valeur"), (int, float))
                and isfinite(value["Valeur"])
            )
        if key.startswith("VR") and isinstance(value, str):
            try:
                int(value)
            except ValueError:
                return False
            return True
        return isinstance(value, (int, float)) and isfinite(value)

    @callback
    def register_fields(self, keys: tuple[str, ...]) -> None:
        """Track only fields used by loaded entities, using their own mappings."""
        for key in keys:
            self._required_fields[key] = self._required_fields.get(key, 0) + 1
            if (
                key not in self.field_receipt_times
                and self._last_read_time is not None
                and self._valid_field(key, (self.data or {}).get(key))
            ):
                self.field_receipt_times[key] = self._last_read_time

    @callback
    def unregister_fields(self, keys: tuple[str, ...]) -> None:
        """Stop tracking fields no longer used by any entity."""
        for key in keys:
            count = self._required_fields.get(key, 0)
            if count > 1:
                self._required_fields[key] = count - 1
            else:
                self._required_fields.pop(key, None)
                self.field_receipt_times.pop(key, None)
                self._missing_fields.pop(key, None)
        self._schedule_freshness_expiry()

    def fields_available(self, *keys: str) -> bool:
        """Require each field to have usable poll data or a recent direct push."""
        now = monotonic()
        return self.data is not None and all(
            key in self.data
            and (
                key not in self._required_fields
                or self._valid_field(key, self.data[key])
            )
            and (
                key not in self._missing_fields
                or now < self._missing_fields[key][0] + 2 * self.recovery_delay
            )
            and (
                self.data_available
                or now - self.field_push_times.get(key, float("-inf")) < self.push_ttl
            )
            for key in keys
        )

    @property
    def push_ttl(self) -> float:
        """Bound push-only availability to one scan plus the recovery window."""
        interval = self.update_interval.total_seconds()
        return interval + (MAX_READ_FAILURES - 1) * min(interval, MAX_READ_RETRY_DELAY)

    @callback
    def async_apply_push(self, values: dict) -> None:
        """Merge a validated batch without altering full-read health or timers."""
        if self._shutdown_requested:
            return
        self.data = {**(self.data or {}), **values}
        now = monotonic()
        self.field_push_times.update({key: now for key in values})
        for key in values:
            if key in self._required_fields:
                self.field_receipt_times[key] = now
            self._missing_fields.pop(key, None)
        self._schedule_freshness_expiry()
        self.async_update_listeners()

    @callback
    def _schedule_freshness_expiry(self) -> None:
        """Publish push and omission expiry; this timer never performs reads."""
        if self._freshness_expiry is not None:
            self._freshness_expiry.cancel()
            self._freshness_expiry = None
        deadlines = [time + self.push_ttl for time in self.field_push_times.values()]
        deadlines.extend(
            time + 2 * self.recovery_delay for time, _ in self._missing_fields.values()
        )
        if deadlines and not self._shutdown_requested:
            delay = max(0, min(deadlines) - monotonic())
            self._freshness_expiry = self.hass.loop.call_later(
                delay, self._expire_fields
            )

    @callback
    def _expire_fields(self) -> None:
        """Publish expiry even when all subsequent full reads fail."""
        cutoff = monotonic() - self.push_ttl
        self.field_push_times = {
            key: timestamp
            for key, timestamp in self.field_push_times.items()
            if timestamp > cutoff
        }
        expired = [
            key
            for key, (started, _) in self._missing_fields.items()
            if monotonic() >= started + 2 * self.recovery_delay
        ]
        if expired:
            self.data = dict(self.data or {})
            for key in expired:
                self.data.pop(key, None)
                self._missing_fields.pop(key)
                self.field_receipt_times.pop(key, None)
                self.field_push_times.pop(key, None)
            # Keep the pending recovery read: expiry changes availability, not
            # the acquisition schedule. Its result restores the normal interval.
        self._schedule_freshness_expiry()
        self.async_update_listeners()

    async def async_shutdown(self) -> None:
        """Release push freshness resources with this controller."""
        await super().async_shutdown()
        if self._freshness_expiry is not None:
            self._freshness_expiry.cancel()
            self._freshness_expiry = None
        self.field_push_times.clear()
        self.push_entities.clear()
        self._required_fields.clear()
        self.field_receipt_times.clear()
        self._missing_fields.clear()

    @property
    def data_available(self) -> bool:
        """Return whether a successful snapshot is still usable by entities."""
        return self.data is not None and (self.last_update_success or self._retain_data)

    @callback
    def _schedule_refresh(self) -> None:
        """Do not reschedule a read that finishes while the entry is unloading."""
        if not self._shutdown_requested:
            if self._missing_fields and (
                self.last_update_success
                or isinstance(self.last_exception, IpxTransientReadError)
            ):
                self._retry_after = min(
                    self.recovery_delay,
                    self._retry_after
                    if self._retry_after is not None
                    else self.recovery_delay,
                )
            super()._schedule_refresh()

    async def _async_update_data(self) -> dict:
        """Read once; never present cached data as a successful acquisition."""
        was_available = self.data_available
        # Keep the previous health decision while awaiting I/O: a direct push
        # may notify listeners during a recovery read.
        read_started = monotonic()
        self._read_in_progress = True
        try:
            data = await super()._async_update_data()
        except Ipx800InvalidAuthError as err:
            self._retain_data = False
            raise ConfigEntryAuthFailed("IPX800 authentication failed") from err
        except Ipx800RequestError as err:
            self._retain_data = False
            raise ConfigEntryError("IPX800 rejected the API request") from err
        except (Ipx800CannotConnectError, TimeoutError) as err:
            self._retain_data = False
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
            retry_delay = self.recovery_delay if self._retain_data else None
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
        except Exception:
            self._retain_data = False
            raise
        finally:
            self._read_in_progress = False

        self._retain_data = False
        self.consecutive_failures = 0
        self.last_successful_read = dt_util.utcnow()
        now = monotonic()
        self._last_read_time = now
        # A response requested before a push must not overwrite that newer value.
        self.field_push_times = {
            key: timestamp
            for key, timestamp in self.field_push_times.items()
            if timestamp > read_started
        }
        data = dict(data)
        for key in self.field_push_times:
            data[key] = self.data[key]
        for key in self._required_fields:
            if self._valid_field(key, data.get(key)):
                self.field_receipt_times[key] = self.field_push_times.get(key, now)
                self._missing_fields.pop(key, None)
                continue
            data.pop(key, None)
            if key not in self.field_receipt_times:
                continue  # Never received (or already expired): no fast retries.
            started, count = self._missing_fields.get(key, (now, 0))
            count += 1
            if count >= MAX_READ_FAILURES or now >= started + 2 * self.recovery_delay:
                self._missing_fields.pop(key, None)
                self.field_receipt_times.pop(key, None)
                self.field_push_times.pop(key, None)
            else:
                self._missing_fields[key] = (started, count)
                data[key] = self.data[key]
        self._schedule_freshness_expiry()
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
