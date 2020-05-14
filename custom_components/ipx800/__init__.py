"""Support for the ipx800."""
from collections import defaultdict
import asyncio
import logging

from pypx800 import IPX800 as pypx800

from aiohttp import web

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.const import KEY_REAL_IP
from homeassistant.helpers.entity import Entity

# from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import discovery
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
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

CONF_GATEWAYS = "gateways"
CONF_DEVICES_CONFIG = "devices_config"
CONF_DEVICE_COMPONENT = "component"
CONF_RELAY = "relay"
CONF_XPWM = "xpwm"
CONF_XPWM_RGB = "xpwm_rgb"
CONF_XPWM_RGBW = "xpwm_rgbw"
CONF_XDIMMER = "xdimmer"
CONF_VIRTUALOUT = "virtualout"
CONF_VIRTUALIN = "virtualin"
CONF_ANALOGIN = "analogin"
CONF_DIGITALIN = "digitalin"
CONF_TRANSITION = "transition"
CONF_SHOULD_POLL = "should_poll"
DEFAULT_TRANSITION = 0.5
DOMAIN = "ipx800"
IPX800_CONTROLLERS = "ipx800_controllers"
IPX800_DEVICES = "ipx800_devices"
IPX800_COMPONENTS = ["light", "switch", "sensor", "binary_sensor"]

DEVICE_CONFIG_SCHEMA_ENTRY = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_DEVICE_COMPONENT): cv.string,
        vol.Optional(CONF_SHOULD_POLL, default=True): cv.boolean,
        vol.Optional(CONF_RELAY): cv.positive_int,
        vol.Optional(CONF_XPWM): cv.positive_int,
        vol.Optional(CONF_XPWM_RGB): cv.ensure_list,
        vol.Optional(CONF_XPWM_RGBW): cv.ensure_list,
        vol.Optional(CONF_XDIMMER): cv.positive_int,
        vol.Optional(CONF_VIRTUALOUT): cv.positive_int,
        vol.Optional(CONF_VIRTUALIN): cv.positive_int,
        vol.Optional(CONF_ANALOGIN): cv.positive_int,
        vol.Optional(CONF_DIGITALIN): cv.positive_int,
        vol.Optional(CONF_ICON): cv.icon,
        vol.Optional(CONF_TRANSITION): cv.positive_int,
        vol.Optional(CONF_DEVICE_CLASS): cv.string,
        vol.Optional(CONF_UNIT_OF_MEASUREMENT): cv.string,
    }
)

GATEWAY_CONFIG = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=80): cv.port,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_DEVICES_CONFIG, default={}): vol.Schema(
            {cv.string: DEVICE_CONFIG_SCHEMA_ENTRY}
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {vol.Required(CONF_GATEWAYS): vol.All(cv.ensure_list, [GATEWAY_CONFIG])}
        )
    },
    extra=vol.ALLOW_EXTRA,
)


class Ipx800Controller:
    """Initiate ipx800 Controller Class."""

    def __init__(self, config):
        """Initialize the ipx800 controller."""
        self.name = config[CONF_HOST]
        _LOGGER.debug("Initialize the gateway %s.", self.name)

        self.ipx = pypx800(
            config[CONF_HOST],
            str(config[CONF_PORT]),
            config[CONF_API_KEY],
            config[CONF_USERNAME],
            config[CONF_PASSWORD],
        )
        # devices config from user
        self._devices_config = config[CONF_DEVICES_CONFIG]
        # devices by type after verifications
        self.ipx_devices = defaultdict(list)

    def _read_devices(self):
        """Read and process the device list."""
        self.fibaro_devices = defaultdict(list)
        _LOGGER.debug("Read and process devices configuration")
        for device in self._devices_config:
            try:
                device_config = self._devices_config.get(device, {})
                if device_config[CONF_DEVICE_COMPONENT] not in IPX800_COMPONENTS:
                    _LOGGER.error(
                        "Device %s skipped: component %s not correct or supported.",
                        device_config[CONF_NAME],
                        device_config[CONF_DEVICE_COMPONENT],
                    )
                    continue
                if (
                    sum(
                        [
                            CONF_RELAY in device_config,
                            CONF_XDIMMER in device_config,
                            CONF_XPWM in device_config,
                            CONF_XPWM_RGB in device_config,
                            CONF_XPWM_RGBW in device_config,
                            CONF_VIRTUALOUT in device_config,
                            CONF_VIRTUALIN in device_config,
                            CONF_ANALOGIN in device_config,
                            CONF_DIGITALIN in device_config,
                        ]
                    )
                    != 1
                ):
                    _LOGGER.error(
                        "Device %s skipped: only type of command must be set: relay, xdimmer, xpwm, vi, vo....",
                        device_config[CONF_NAME],
                    )
                    continue
                # Build device to add to hass
                ipx_device = {}
                ipx_device["name"] = device
                ipx_device["controller"] = self
                ipx_device["config"] = device_config
                self.ipx_devices[device_config[CONF_DEVICE_COMPONENT]].append(
                    ipx_device
                )
                _LOGGER.info(
                    "Device %s added (device component: %s).",
                    device_config[CONF_NAME],
                    device_config[CONF_DEVICE_COMPONENT],
                )
            except (KeyError, ValueError) as error:
                _LOGGER.error(
                    "Error to handle device %s: %s.", device_config[CONF_NAME], error
                )

    def api_transmit(self, command):
        """
            Transmit API request command
            command: must be like 'ipx800/VO1=on'
        """
        _LOGGER.debug(
            "===> Receive API request command %s for gateway %s.", command, self.name
        )
        device_type = command[command.index("ipx800/") + 7 : command.index("=")]
        value = bool(command[command.index("=") + 1] in "on", 1, True, "true")
        self._update_device(device_type, value)

    def update_device(self, device_type, value):
        """ Update state of device """


def setup(hass, config):
    """Set up the IPX800 Component."""
    hass.data[IPX800_CONTROLLERS] = {}
    hass.data[IPX800_DEVICES] = {}

    # Provide an endpoint for the IPX to call to trigger events
    hass.http.register_view(IpxRequestView)

    for component in IPX800_COMPONENTS:
        hass.data[IPX800_DEVICES][component] = []

    for gateway in config[DOMAIN][CONF_GATEWAYS]:
        controller = Ipx800Controller(gateway)
        if controller.ipx.ping():
            _LOGGER.info("Successfully connected to the gateway %s.", controller.name)
            controller._read_devices()
            hass.data[IPX800_CONTROLLERS][controller.name] = controller
            for component in IPX800_COMPONENTS:
                hass.data[IPX800_DEVICES][component].extend(
                    controller.ipx_devices[component]
                )
        else:
            _LOGGER.error(
                "Can't connect to the gateway %s, please check host, port and api_key.",
                controller.name,
            )

    if hass.data[IPX800_CONTROLLERS]:
        for component in IPX800_COMPONENTS:
            _LOGGER.debug("Load component %s.", component)
            discovery.load_platform(hass, component, DOMAIN, {}, config)
        return True
    else:
        return False


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


class IpxDevice(Entity):
    """Representation of a IPX800 device entity."""

    def __init__(self, ipx_device):
        """Initialize the device."""
        # self.coordinator = coordinator
        self.config = ipx_device.get("config")
        self.controller = ipx_device.get("controller")
        self._name = self.config.get(CONF_NAME)

        self._device_class = self.config.get(CONF_DEVICE_CLASS) or None
        self._unit_of_measurement = self.config.get(CONF_UNIT_OF_MEASUREMENT) or None
        self._transition = self.config.get(CONF_TRANSITION) or None
        self._icon = self.config.get(CONF_ICON) or None
        self._should_poll = self.config.get(CONF_SHOULD_POLL)
        self._state = None

        self._supported_flags = 0
        self._uid = (
            f"{self.controller.name}.{self.config.get('device_class')}.{ipx_device.get('name')}"
        ).lower()

        _LOGGER.debug("Init new device : %s", self)

    @property
    def should_poll(self):
        return self._should_poll

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self._name,
            "manufacturer": "GCE",
            "model": "IPX800v4",
            "via_device": (DOMAIN, self.controller.name),
        }

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._uid

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_flags
