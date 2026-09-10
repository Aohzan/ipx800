"""Stateless push routes resolving the current live IPX entry per request."""

from http import HTTPStatus

from aiohttp import BasicAuth, web

from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.http import HomeAssistantView

from .const import (
    CONF_PUSH_CHECK_HOST,
    CONF_PUSH_PASSWORD,
    COORDINATOR,
    DOMAIN,
    PUSH_CONFIG,
    PUSH_USERNAME,
    TYPE_DIGITALIN,
    TYPE_RELAY,
    TYPE_VIRTUALIN,
    TYPE_VIRTUALOUT,
)


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

    def _entity(self, hass, coordinator, entity_id):
        """Resolve only an active entity belonging to the receiving config entry."""
        registry_entry = er.async_get(hass).async_get(entity_id)
        if (
            registry_entry is None
            or registry_entry.platform != DOMAIN
            or registry_entry.config_entry_id != coordinator.config_entry.entry_id
        ):
            raise web.HTTPNotFound(text="Unknown entity for this IPX")
        entity = coordinator.push_entities.get(registry_entry.unique_id)
        if entity is None or entity.entity_id != entity_id:
            raise web.HTTPNotFound(text="Entity is not loaded")
        return entity

    def _apply(self, coordinator, updates):
        """Validate every value and shared-field conflict before publishing."""
        values = {}
        try:
            for entity, state in updates:
                for key, value in entity.push_values(state).items():
                    if key in values and values[key] != value:
                        raise ValueError("Conflicting values for the same IPX field")
                    values[key] = value
        except ValueError as err:
            raise web.HTTPBadRequest(text=str(err)) from None
        if not values:
            raise web.HTTPBadRequest(text="No supported fields in payload")
        coordinator.async_apply_push(values)
        return web.Response(status=HTTPStatus.OK, text="OK")


class IpxRequestView(IpxPushView):
    """Provide a page for the device to call."""

    requires_auth = False
    url = "/api/ipx800v4/{entity_id}/{state}"
    name = "api:ipx800v4"
    extra_urls = ["/api/ipx800v4/{ipx_name}/{entity_id}/{state}"]

    async def get(self, request, entity_id, state, ipx_name=None):
        """Respond to requests from the device."""
        coordinator = self._entry(request, ipx_name)[COORDINATOR]
        entity = self._entity(request.app["hass"], coordinator, entity_id)
        return self._apply(coordinator, [(entity, state)])


class IpxRequestDataView(IpxPushView):
    """Provide a page for the device to call for send multiple data at once."""

    requires_auth = False
    url = "/api/ipx800v4_data/{data}"
    name = "api:ipx800v4_data"
    extra_urls = ["/api/ipx800v4_data/{ipx_name}/{data}"]

    async def get(self, request, data, ipx_name=None):
        """Respond to requests from the device."""
        coordinator = self._entry(request, ipx_name)[COORDINATOR]
        updates = []
        for item in data.split("&"):
            if item.count("=") != 1:
                raise web.HTTPBadRequest(text="Expected entity_id=value pairs")
            entity_id, state = item.split("=", 1)
            if not entity_id or not state:
                raise web.HTTPBadRequest(text="Empty entity or value")
            entity = self._entity(request.app["hass"], coordinator, entity_id)
            updates.append((entity, state))
        return self._apply(coordinator, updates)


class IpxRequestBulkUpdateView(IpxPushView):
    """Provide a page for the device to call for bulk update all states at once."""

    requires_auth = False
    url = "/api/ipx800v4_bulk/{device_type}/{data}"
    name = "api:ipx800v4_bulk"
    extra_urls = ["/api/ipx800v4_bulk/{ipx_name}/{device_type}/{data}"]

    async def get(self, request, device_type, data, ipx_name=None):
        """Respond to requests from the device."""
        coordinator = self._entry(request, ipx_name)[COORDINATOR]
        supported_types = {
            TYPE_RELAY, TYPE_DIGITALIN, TYPE_VIRTUALIN, TYPE_VIRTUALOUT,
        }
        if (
            device_type not in supported_types
            or not data
            or any(bit not in "01" for bit in data)
        ):
            raise web.HTTPBadRequest(
                text="Expected a supported binary type and bit string"
            )
        # Use live registry entries, including renamed IDs. Bulk bits are raw
        # hardware values: platform properties apply their own inversion once.
        values = {}
        registry = er.async_get(request.app["hass"])
        for entry in er.async_entries_for_config_entry(
            registry, coordinator.config_entry.entry_id
        ):
            if entry.platform != DOMAIN:
                continue
            entity = coordinator.push_entities.get(entry.unique_id)
            if entity is None or entity.entity_id != entry.entity_id:
                continue
            if entity._ipx_type != device_type or not entity._push_binary:
                continue
            index = entity._id - 1
            if 0 <= index < len(data):
                values[entity.push_key] = int(data[index])
        if not values:
            raise web.HTTPBadRequest(text="No loaded targets in payload")
        coordinator.async_apply_push(values)
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
