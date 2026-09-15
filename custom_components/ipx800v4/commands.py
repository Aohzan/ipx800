"""Single-attempt command transport and bounded, non-blocking write retries."""

import asyncio
import logging
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from contextvars import ContextVar
from json import JSONDecodeError
from typing import Any

from aiohttp import (
    BasicAuth,
    ClientError,
    ClientResponseError,
    ContentTypeError,
    InvalidURL,
)
from homeassistant.exceptions import HomeAssistantError
from pypx800 import (
    IPX800,
    Ipx800CannotConnectError,
    Ipx800InvalidAuthError,
    Ipx800RequestError,
)

_LOGGER = logging.getLogger(__name__)
RETRY_DELAYS = (1, 2)
_CURRENT_COMMAND: ContextVar[Callable[[], None]] = ContextVar("ipx_command_check")


class IpxCommandClient(IPX800):
    """Avoid pypx800 2.5.1's blocking sleep even after a single CGI failure."""

    async def request_api(self, params: dict) -> dict:
        """Check HTTP status and bound the complete JSON response read."""
        try:
            async with asyncio.timeout(self._request_timeout):
                response = await self._session.get(
                    self._api_url, params={"key": self._api_key, **params}
                )
                try:
                    if response.status in (401, 403):
                        raise Ipx800InvalidAuthError("IPX800 authentication failed")
                    response.raise_for_status()
                    content = await response.json()
                finally:
                    response.close()
            if not isinstance(content, dict):
                raise Ipx800RequestError("IPX800 returned an unexpected JSON structure")
            if not self._request_checkstatus or content.get("status") == "Success":
                return content
            raise Ipx800RequestError("IPX800 response did not confirm success")
        except (TimeoutError, ClientError, socket.gaierror) as err:
            raise Ipx800CannotConnectError("IPX800 communication failed") from err
        except (JSONDecodeError, UnicodeDecodeError) as err:
            raise Ipx800RequestError("IPX800 returned invalid JSON content") from err

    async def request_cgi(self, params: dict) -> str:
        """Send once; keep retries at the explicitly opted-in operation level."""
        auth = None
        if self._username and self._password:
            auth = BasicAuth(self._username, self._password)
        try:
            async with asyncio.timeout(self._request_timeout):
                response = await self._session.get(
                    self._cgi_url, auth=auth, params=params
                )
                try:
                    if response.status in (401, 403):
                        raise Ipx800InvalidAuthError("IPX800 authentication failed")
                    response.raise_for_status()
                    content = await response.text()
                finally:
                    response.close()
            if not self._request_checkstatus or "Success" in content:
                return content
            raise Ipx800RequestError("IPX800 response did not confirm success")
        except (TimeoutError, ClientError, socket.gaierror) as err:
            raise Ipx800CannotConnectError("IPX800 communication failed") from err

        except UnicodeDecodeError as err:
            raise Ipx800RequestError(
                "IPX800 returned invalid response content"
            ) from err


def error_details(error: Exception) -> tuple[str, bool]:
    """Return a secret-free reason and whether replay may recover the failure."""
    cause = error.__cause__
    if isinstance(error, Ipx800InvalidAuthError):
        return "authentication failed", False
    if isinstance(error, InvalidURL) or isinstance(cause, InvalidURL):
        return "invalid request URL", False
    # HTTP status takes precedence, including ContentTypeError on a 4xx.
    if isinstance(cause, ClientResponseError):
        if cause.status in (401, 403):
            return f"authentication failed (HTTP {cause.status})", False
        if cause.status >= 400:
            return f"HTTP {cause.status}", cause.status in (
                408,
                429,
            ) or 500 <= cause.status < 600
        if isinstance(cause, ContentTypeError):
            return "unexpected response content type", True
    if isinstance(error, TimeoutError) or isinstance(cause, TimeoutError):
        return "request timeout", True
    if isinstance(cause, (JSONDecodeError, UnicodeDecodeError)):
        return "invalid response content", True
    if isinstance(error, Ipx800RequestError):
        return "response did not confirm success", True
    return "connection or response transfer failed", True


class CommandFailure(Exception):
    """Carry the failed write's real attempt count without exposing its URL."""

    def __init__(self, error: Exception, attempts: int, retry_enabled: bool) -> None:
        self.error = error
        reason, retryable = error_details(error)
        cause = error.__cause__
        kind = type(error).__name__
        if cause is not None:
            kind += f" / {type(cause).__name__}"
        policy = (
            "retries disabled for this command"
            if not retry_enabled
            else "non-retryable error"
            if not retryable
            else "retry limit reached"
        )
        super().__init__(
            f"IPX800 {reason} ({kind}); attempts: {attempts}, "
            f"retries: {attempts - 1}; {policy}"
        )


class CommandManager:
    """Coordinate overlapping outputs, including aliases in different platforms."""

    def __init__(self) -> None:
        self._closed = False
        self._versions: dict[str, object] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def shutdown(self) -> None:
        """Prevent pending retries or remaining writes after entry unload."""
        self._closed = True

    @asynccontextmanager
    async def operation(self, keys: tuple[str, ...]) -> AsyncIterator[None]:
        # Register intent before waiting for an in-flight write. An older
        # operation must not retry or write its remaining channels afterwards.
        version = object()
        for key in keys:
            self._versions[key] = version

        def check_current() -> None:
            if self._closed:
                raise HomeAssistantError("IPX800 integration is unloading")
            if any(self._versions[key] is not version for key in keys):
                raise HomeAssistantError("IPX800 command superseded by a newer command")

        token = _CURRENT_COMMAND.set(check_current)
        try:
            yield
        finally:
            _CURRENT_COMMAND.reset(token)

    async def write(
        self,
        keys: tuple[str, ...],
        command: Callable[..., Awaitable[Any]],
        *args: Any,
        retry: bool = False,
        **kwargs: Any,
    ) -> None:
        """Retry one fixed write; release locks during asynchronous backoff."""
        for attempt in range(len(RETRY_DELAYS) + 1 if retry else 1):
            _CURRENT_COMMAND.get()()
            try:
                async with AsyncExitStack() as stack:
                    for key in sorted(set(keys)):
                        await stack.enter_async_context(
                            self._locks.setdefault(key, asyncio.Lock())
                        )
                    _CURRENT_COMMAND.get()()
                    await command(*args, **kwargs)
                return
            except (
                Ipx800CannotConnectError,
                Ipx800RequestError,
                Ipx800InvalidAuthError,
                TimeoutError,
            ) as err:
                if (
                    not retry
                    or attempt == len(RETRY_DELAYS)
                    or not error_details(err)[1]
                ):
                    raise CommandFailure(err, attempt + 1, retry) from err
                _CURRENT_COMMAND.get()()
                _LOGGER.debug(
                    "IPX800 write failed (%s); attempt %s/%s in %ss",
                    type(err).__name__,
                    attempt + 2,
                    len(RETRY_DELAYS) + 1,
                    RETRY_DELAYS[attempt],
                )
                await asyncio.sleep(RETRY_DELAYS[attempt])
