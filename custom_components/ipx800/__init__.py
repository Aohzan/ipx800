"""Support for the ipx800."""
from collections import defaultdict
from datetime import timedelta
import asyncio
import async_timeout
import logging

from pypx800 import *

from .const import *

from aiohttp import web

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.components.http import HomeAssistantView

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import discovery
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_API_KEY,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_NAME,
    CONF_ICON,
    CONF_DEVICE_CLASS,
    CONF_UNIT_OF_MEASUREMENT,
    HTTP_OK,
)

_LOGGER = logging.getLogger(__name__)

DEVICE_CONFIG_SCHEMA_ENTRY = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_COMPONENT): cv.string,
        vol.Required(CONF_TYPE): cv.string,
        vol.Optional(CONF_ID): cv.positive_int,
        vol.Optional(CONF_IDS): cv.ensure_list,
        vol.Optional(CONF_EXT_ID): cv.positive_int,
        vol.Optional(CONF_ICON): cv.icon,
        vol.Optional(CONF_TRANSITION, default=DEFAULT_TRANSITION): vol.Coerce(float),
        vol.Optional(CONF_DEVICE_CLASS): cv.string,
        vol.Optional(CONF_UNIT_OF_MEASUREMENT): cv.string,
    }
)

GATEWAY_CONFIG = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=80): cv.port,
        vol.Optional(CONF_SCAN_INTERVAL, default=5): cv.positive_int,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_DEVICES, default=[]): vol.All(
            cv.ensure_list, [DEVICE_CONFIG_SCHEMA_ENTRY]
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [GATEWAY_CONFIG])}, extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Set up the IPX800 Component."""
    hass.data.setdefault(DOMAIN, {})

    # Provide an endpoint for the IPX to call to push states
    hass.http.register_view(IpxRequestView)

    if DOMAIN in config:
        for gateway in config[DOMAIN]:
            controller = IpxController(hass, gateway)

            ping = await hass.async_add_executor_job(controller.ipx.ping)

            if ping:
                _LOGGER.info(
                    "Successfully connected to the IPX800 %s.", controller.name
                )

                await controller.coordinator.async_refresh()

                hass.data[DOMAIN][controller.name] = controller
                controller.read_devices()

                for component in CONF_COMPONENT_ALLOWED:
                    _LOGGER.debug("Load component %s.", component)

                    discovery.load_platform(
                        hass,
                        component,
                        DOMAIN,
                        list(
                            filter(
                                lambda item: item.get(
                                    "config").get(CONF_COMPONENT)
                                == component,
                                controller.devices,
                            )
                        ),
                        config,
                    )
            else:
                _LOGGER.error(
                    "Can't connect to the IPX800 %s, please check host, port and api_key.",
                    controller.name,
                )

    return True


class IpxController:
    """Initiate ipx800 Controller Class."""

    def __init__(self, hass, config):
        """Initialize the ipx800 controller."""
        _LOGGER.debug("New IPX800 initialisation on host: %s",
                      config.get(CONF_HOST))

        self.name = config[CONF_NAME]

        self.ipx = IPX800(
            config[CONF_HOST],
            str(config[CONF_PORT]),
            config[CONF_API_KEY],
            config.get(CONF_USERNAME),
            config.get(CONF_PASSWORD),
        )

        self.coordinator = IpxDataUpdateCoordinator(
            hass=hass,
            ipx=self.ipx,
            update_interval=timedelta(seconds=config.get(CONF_SCAN_INTERVAL)),
        )

        # devices config from user
        self._devices_config = config.get(CONF_DEVICES, [])
        # devices by type after verifications
        self.devices = []

    def read_devices(self):
        """Read and process the device list."""
        _LOGGER.debug("Read and process devices configuration")
        for device_config in self._devices_config:
            device = {}
            _LOGGER.debug("Read device name: %s", device_config.get(CONF_NAME))
            try:
                """Check if component is supported"""
                if device_config[CONF_COMPONENT] not in CONF_COMPONENT_ALLOWED:
                    _LOGGER.error(
                        "Device %s skipped: %s %s not correct or supported.",
                        device_config[CONF_NAME],
                        CONF_COMPONENT,
                        device_config[CONF_COMPONENT],
                    )
                    continue

                """Check if type is supported"""
                if device_config[CONF_TYPE] not in CONF_TYPE_ALLOWED:
                    _LOGGER.error(
                        "Device %s skipped: %s %s not correct or supported.",
                        device_config[CONF_NAME],
                        CONF_TYPE,
                        device_config[CONF_TYPE],
                    )
                    continue

                """Check if X4VR have extension id set"""
                if (
                    device_config[CONF_TYPE] == TYPE_X4VR
                    and CONF_EXT_ID not in device_config
                ):
                    _LOGGER.error(
                        "Device %s skipped: %s must have %s set.",
                        device_config[CONF_NAME],
                        TYPE_X4VR,
                        CONF_EXT_ID,
                    )
                    continue

                """Check if RGB/RBW or FP/RELAY have ids set"""
                if (
                    (device_config[CONF_TYPE] == TYPE_XPWM_RGB
                    or device_config[CONF_TYPE] == TYPE_XPWM_RGBW
                    or (device_config[CONF_TYPE] == TYPE_RELAY and device_config[CONF_COMPONENT] == "climate"))
                    and CONF_IDS not in device_config
                ):
                    _LOGGER.error(
                        "Device %s skipped: RGB/RGBW must have %s set.",
                        device_config[CONF_NAME],
                        CONF_IDS,
                    )
                    continue

                """Check if other device types have id set"""
                if (
                    device_config[CONF_TYPE] != TYPE_XPWM_RGB
                    and device_config[CONF_TYPE] != TYPE_XPWM_RGBW
                    and not (device_config[CONF_TYPE] == TYPE_RELAY and device_config[CONF_COMPONENT] == "climate")
                    and CONF_ID not in device_config
                ):
                    _LOGGER.error(
                        "Device %s skipped: must have %s set.",
                        device_config[CONF_NAME],
                        CONF_ID,
                    )
                    continue

                device["config"] = device_config
                device["controller"] = self
                self.devices.append(device)
                _LOGGER.info(
                    "Device %s added (component: %s).",
                    device_config[CONF_NAME],
                    device_config[CONF_COMPONENT],
                )
            except:
                _LOGGER.error(
                    "Error to handle device %s. Please check its config",
                    device_config.get(CONF_NAME),
                )


class IpxRequestView(HomeAssistantView):
    """Provide a page for the device to call."""

    requires_auth = False
    url = "/api/ipx800/{entity_id}/{state}"
    name = "api:ipx800"

    async def get(self, request, entity_id, state):
        """Respond to requests from the device."""
        hass = request.app["hass"]
        old_state = hass.states.get(entity_id)
        _LOGGER.debug("Update %s to state %s.", entity_id, state)
        if old_state:
            hass.states.async_set(entity_id, state, old_state.attributes)
            return web.Response(status=HTTP_OK, text="OK")
        else:
            _LOGGER.warning("Entity not found.")


class IpxDataUpdateCoordinator(DataUpdateCoordinator):
    """Define an object to hold ipx data."""

    def __init__(self, hass, ipx, update_interval):
        """Initialize."""
        self.ipx = ipx
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)

    async def _async_update_data(self):
        """Get all states from API."""
        return await self.hass.async_add_executor_job(self.ipx.global_get)
