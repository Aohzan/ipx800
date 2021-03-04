"""Support for the GCE IPX800 V4."""
import asyncio
from datetime import timedelta
import logging
import re

from aiohttp import web
from pypx800 import *
import voluptuous as vol

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_DEVICE_CLASS,
    CONF_HOST,
    CONF_ICON,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_USERNAME,
    HTTP_OK,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, discovery
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import (
    REQUEST_REFRESH_DEFAULT_IMMEDIATE,
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import *

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
        vol.Optional(CONF_SCAN_INTERVAL, default=10): cv.positive_int,
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
    {DOMAIN: vol.All(cv.ensure_list, [GATEWAY_CONFIG])},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Set up the IPX800 from config file."""
    gateways = config.get(DOMAIN)
    if not gateways:
        return True

    for gateway in gateways:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=gateway
            )
        )

    return True


async def async_setup_entry(hass, config_entry):
    """Set up the IPX800."""
    hass.data.setdefault(DOMAIN, {})

    gateway_config = config_entry.data

    # Provide endpoints for the IPX to call to push states
    hass.http.register_view(IpxRequestView)
    hass.http.register_view(IpxRequestDataView)

    controller = IpxController(hass, gateway_config)

    ping = await hass.async_add_executor_job(controller.ipx.ping)

    if ping:
        _LOGGER.debug(
            "Successfully connected to the IPX800 with name: %s.", controller.name
        )

        await controller.coordinator.async_refresh()

        undo_listener = config_entry.add_update_listener(_async_update_listener)

        hass.data[DOMAIN][config_entry.entry_id] = {
            CONTROLLER: controller,
            UNDO_UPDATE_LISTENER: undo_listener,
        }

        controller.read_devices()

        device_registry = await dr.async_get_registry(hass)
        device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, controller.name)},
            manufacturer="GCE",
            model="IPX800 V4",
            name=controller.name,
        )

        for component in CONF_COMPONENT_ALLOWED:
            _LOGGER.debug(f"Load component %s.", component)
            hass.async_create_task(
                hass.config_entries.async_forward_entry_setup(config_entry, component)
            )

        return True
    else:
        _LOGGER.error(
            "Can't connect to the IPX800 named %s, please check host, port and api_key.",
            controller.name,
        )
    return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in CONF_COMPONENT_ALLOWED
            ]
        )
    )

    if unload_ok:
        hass.data[DOMAIN][entry.entry_id][UNDO_UPDATE_LISTENER]()
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok


async def _async_update_listener(hass, config_entry):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


class IpxController:
    """Initiate ipx800 Controller Class."""

    def __init__(self, hass, config):
        """Initialize the ipx800 controller."""
        _LOGGER.debug("New IPX800 initialisation on host %s", config.get(CONF_HOST))

        self.name = config[CONF_NAME]

        self.ipx = IPX800(
            config[CONF_HOST],
            str(config[CONF_PORT]),
            config[CONF_API_KEY],
            config.get(CONF_USERNAME),
            config.get(CONF_PASSWORD),
        )

        scan_interval = config.get(CONF_SCAN_INTERVAL)
        self.coordinator = IpxDataUpdateCoordinator(
            hass=hass,
            ipx=self.ipx,
            update_interval=timedelta(seconds=scan_interval),
        )

        # devices config from user
        self._devices_config = config.get(CONF_DEVICES, [])
        # devices by type after verifications
        self.devices = []

    def read_devices(self):
        """Read and process the device list."""
        _LOGGER.debug("Read and process devices configuration")
        for device_config in self._devices_config:
            _LOGGER.debug(f"Read device name: {device_config.get(CONF_NAME)}")
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
                    device_config[CONF_TYPE] == TYPE_XPWM_RGB
                    or device_config[CONF_TYPE] == TYPE_XPWM_RGBW
                    or (
                        device_config[CONF_TYPE] == TYPE_RELAY
                        and device_config[CONF_COMPONENT] == "climate"
                    )
                ) and CONF_IDS not in device_config:
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
                    and not (
                        device_config[CONF_TYPE] == TYPE_RELAY
                        and device_config[CONF_COMPONENT] == "climate"
                    )
                    and CONF_ID not in device_config
                ):
                    _LOGGER.error(
                        "Device %s skipped: must have %s set.",
                        device_config[CONF_NAME],
                        CONF_ID,
                    )
                    continue

                device_config[CONTROLLER] = self.name
                self.devices.append(device_config)
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
    url = "/api/ipx800v4/{entity_id}/{state}"
    name = "api:ipx800v4"

    async def get(self, request, entity_id, state):
        """Respond to requests from the device."""
        hass = request.app["hass"]
        old_state = hass.states.get(entity_id)
        _LOGGER.debug("Update %s to state %s.", entity_id, state)
        if old_state:
            hass.states.async_set(entity_id, state, old_state.attributes)
            return web.Response(status=HTTP_OK, text="OK")
        else:
            _LOGGER.warning("Entity not found for state updating: %s", entity_id)


class IpxRequestDataView(HomeAssistantView):
    """Provide a page for the device to call for send multiple data at once."""

    requires_auth = False
    url = "/api/ipx800v4_data/{data}"
    name = "api:ipx800v4_data"

    async def get(self, request, data):
        """Respond to requests from the device."""
        hass = request.app["hass"]
        entities_data = data.split("&")
        for entity_data in entities_data:
            entity_id = entity_data.split("=")[0]
            state = "on" if entity_data.split("=")[1] in ["1", "on", "true"] else "off"

            old_state = hass.states.get(entity_id)
            _LOGGER.debug("Update %s to state %s.", entity_id, state)
            if old_state:
                hass.states.async_set(entity_id, state, old_state.attributes)
            else:
                _LOGGER.warning("Entity not found for state updating: %s", entity_id)

        return web.Response(status=HTTP_OK, text="OK")


class IpxDataUpdateCoordinator(DataUpdateCoordinator):
    """Define an object to hold ipx data."""

    def __init__(self, hass, ipx, update_interval):
        """Initialize."""
        _LOGGER.debug(
            "Define the coordinator to poll the IPX800 every %s seconds.",
            update_interval.seconds,
        )
        self.ipx = ipx
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=2,
                immediate=IpxDataUpdateCoordinator,
                function=self.async_refresh,
            ),
        )

    async def _async_update_data(self):
        """Get all states from API."""
        return await self.hass.async_add_executor_job(self.ipx.global_get)


class IpxDevice(CoordinatorEntity):
    """Representation of a IPX800 generic device entity."""

    def __init__(self, device_config, controller: IpxController, suffix_name=""):
        """Initialize the device."""
        super().__init__(controller.coordinator)

        self._name = device_config.get(CONF_NAME)
        self._device_name = self._name
        if suffix_name:
            self._name += f" {suffix_name}"

        self._device_class = device_config.get(CONF_DEVICE_CLASS)
        self._unit_of_measurement = device_config.get(CONF_UNIT_OF_MEASUREMENT)
        self._transition = int(
            device_config.get(CONF_TRANSITION, DEFAULT_TRANSITION) * 1000
        )
        self._icon = device_config.get(CONF_ICON)
        self._ipx_type = device_config.get(CONF_TYPE)
        self._component = device_config.get(CONF_COMPONENT)
        self._id = device_config.get(CONF_ID)
        self._ext_id = device_config.get(CONF_EXT_ID)
        self._ids = device_config.get(CONF_IDS, [])

        self._supported_features = 0
        self._controller_name = controller.name

        self._unique_id = self._generate_unique_id(self._name)
        self._device_unique_id = self._generate_unique_id(self._device_name)

    def _generate_unique_id(self, name):
        return (
            f"{self._controller_name}_{self._component}_{re.sub('[^A-Za-z0-9_]+', '', name.replace(' ', '_'))}"
        ).lower()

    @property
    def should_poll(self):
        """No polling since coordinator used"""
        return False

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_unique_id)},
            "name": self._device_name,
            "manufacturer": "GCE",
            "model": "IPX800 V4",
            "via_device": (DOMAIN, self._controller_name),
            "connections": {(DOMAIN, self._ipx_type)},
        }

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._unique_id

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_features

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update the entity."""
        await self.coordinator.async_request_refresh()
