"""Stateless push routes resolving the current live IPX entry per request."""

from http import HTTPStatus
import logging

from aiohttp import BasicAuth, web

from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.http import HomeAssistantView
from homeassistant.util import slugify

from .const import (
    CONF_COMPONENT,
    CONF_DEVICES,
    CONF_ID,
    CONF_INVERT_VALUE,
    CONF_PUSH_CHECK_HOST,
    CONF_PUSH_PASSWORD,
    CONF_TYPE,
    COORDINATOR,
    DOMAIN,
    PUSH_CONFIG,
    PUSH_USERNAME,
)

_LOGGER = logging.getLogger(__name__)


class IpxPushView(HomeAssistantView):
    """Resolve named and legacy routes without retaining runtime references."""

    requires_auth = False

    def _entry(self, request, ipx_name):
        """Authenticate exactly one loaded entry; reject ambiguous legacy routes."""
        try:
            auth = BasicAuth.decode(
                request.headers.get("Authorization", ""), encoding="utf-8"
            )
        except ValueError:
            raise web.HTTPUnauthorized() from None
        if auth.login != PUSH_USERNAME:
            raise web.HTTPUnauthorized()

        matches = []
        for entry_data in request.app["hass"].data.get(DOMAIN, {}).values():
            config = entry_data.get(PUSH_CONFIG)
            if config is None or (ipx_name is not None and config[CONF_NAME] != ipx_name):
                continue
            if config[CONF_PUSH_PASSWORD] != auth.password:
                continue
            if (
                config.get(CONF_PUSH_CHECK_HOST, True)
                and request.remote != config[CONF_HOST]
            ):
                continue
            matches.append(entry_data)
        if len(matches) != 1:
            # Never fall through to a different IPX after unloading a named entry.
            raise web.HTTPUnauthorized()
        return matches[0]


class IpxRequestView(IpxPushView):
    """Provide a page for the device to call."""

    requires_auth = False
    url = "/api/ipx800v4/{entity_id}/{state}"
    name = "api:ipx800v4"
    extra_urls = ["/api/ipx800v4/{ipx_name}/{entity_id}/{state}"]

    async def get(self, request, entity_id, state, ipx_name=None):
        """Respond to requests from the device."""
        self._entry(request, ipx_name)
        hass = request.app["hass"]
        old_state = hass.states.get(entity_id)
        _LOGGER.debug("Update %s to state %s", entity_id, state)
        if old_state:
            hass.states.async_set(entity_id, state, old_state.attributes)
            return web.Response(status=HTTPStatus.OK, text="OK")
        _LOGGER.warning("Entity not found for state updating: %s", entity_id)
        return None


class IpxRequestDataView(IpxPushView):
    """Provide a page for the device to call for send multiple data at once."""

    requires_auth = False
    url = "/api/ipx800v4_data/{data}"
    name = "api:ipx800v4_data"
    extra_urls = ["/api/ipx800v4_data/{ipx_name}/{data}"]

    async def get(self, request, data, ipx_name=None):
        """Respond to requests from the device."""
        self._entry(request, ipx_name)
        hass = request.app["hass"]
        entities_data = data.split("&")
        for entity_data in entities_data:
            entity_id = entity_data.split("=")[0]
            state = "on" if entity_data.split("=")[1] in ["1", "on", "true"] else "off"

            old_state = hass.states.get(entity_id)
            _LOGGER.debug("Update %s to state %s", entity_id, state)
            if old_state:
                hass.states.async_set(entity_id, state, old_state.attributes)
            else:
                _LOGGER.warning("Entity not found for state updating: %s", entity_id)

        return web.Response(status=HTTPStatus.OK, text="OK")


class IpxRequestBulkUpdateView(IpxPushView):
    """Provide a page for the device to call for bulk update all states at once."""

    requires_auth = False
    url = "/api/ipx800v4_bulk/{device_type}/{data}"
    name = "api:ipx800v4_bulk"
    extra_urls = ["/api/ipx800v4_bulk/{ipx_name}/{device_type}/{data}"]

    async def get(self, request, device_type, data, ipx_name=None):
        """Respond to requests from the device."""
        entry_data = self._entry(request, ipx_name)
        hass = request.app["hass"]
        _LOGGER.debug(
            "Bulk update %s from %s : %s", device_type, entry_data[CONF_NAME], data
        )
        devices = (
            device
            for platform_devices in entry_data[CONF_DEVICES].values()
            for device in platform_devices
        )
        for device_config in devices:
            if device_config[CONF_TYPE] != device_type or CONF_ID not in device_config:
                continue
            index = int(device_config[CONF_ID]) - 1
            if 0 <= index < len(data):
                entity_id = ".".join(
                    [device_config[CONF_COMPONENT], slugify(device_config[CONF_NAME])]
                )
                invert_value = device_config.get(CONF_INVERT_VALUE, False)
                state = "on" if data[index] == ("0" if invert_value else "1") else "off"
                old_state = hass.states.get(entity_id)
                if old_state:
                    if state != old_state.state:
                        _LOGGER.debug("Update %s to state %s", entity_id, state)
                        hass.states.async_set(entity_id, state, old_state.attributes)
                else:
                    _LOGGER.warning(
                        "Entity not found for state updating: %s", entity_id
                    )
        return web.Response(status=HTTPStatus.OK, text="OK")


class IpxRequestRefreshView(IpxPushView):
    """Provide a page for the device to force refresh data from coordinator."""

    requires_auth = False
    url = "/api/ipx800v4_refresh/{data}"
    name = "api:ipx800v4_refresh"
    extra_urls = ["/api/ipx800v4_refresh/{ipx_name}/{data}"]

    async def get(self, request, data, ipx_name=None):
        """Respond to requests from the device."""
        entry_data = self._entry(request, ipx_name)
        await entry_data[COORDINATOR].async_request_refresh()
        return web.Response(status=HTTPStatus.OK, text="OK")
