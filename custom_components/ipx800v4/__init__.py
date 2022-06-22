"""Support for the GCE IPX800 V4."""
from base64 import b64decode
from datetime import timedelta
from http import HTTPStatus
import logging

from aiohttp import web
from pypx800 import IPX800, Ipx800CannotConnectError, Ipx800InvalidAuthError
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
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import slugify

from .const import (
    CONF_COMPONENT,
    CONF_COMPONENT_ALLOWED,
    CONF_DEFAULT_BRIGHTNESS,
    CONF_DEVICES,
    CONF_EXT_ID,
    CONF_ID,
    CONF_IDS,
    CONF_PUSH_PASSWORD,
    CONF_TRANSITION,
    CONF_TYPE,
    CONF_TYPE_ALLOWED,
    CONTROLLER,
    COORDINATOR,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRANSITION,
    DOMAIN,
    PUSH_USERNAME,
    REQUEST_REFRESH_DELAY,
    TYPE_ANALOGIN,
    TYPE_COUNTER,
    TYPE_DIGITALIN,
    TYPE_RELAY,
    TYPE_VIRTUALANALOGIN,
    TYPE_VIRTUALIN,
    TYPE_VIRTUALOUT,
    TYPE_X4VR,
    TYPE_X4VR_BSO,
    TYPE_XDIMMER,
    TYPE_XPWM,
    TYPE_XPWM_RGB,
    TYPE_XPWM_RGBW,
    TYPE_XTHL,
    UNDO_UPDATE_LISTENER,
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
        vol.Optional(CONF_DEFAULT_BRIGHTNESS): cv.positive_int,
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
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL): cv.positive_int,
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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the IPX800 from config file."""
    hass.data.setdefault(DOMAIN, {})

    if DOMAIN in config:
        for gateway in config[DOMAIN]:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": SOURCE_IMPORT}, data=gateway
                )
            )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the IPX800v4."""
    hass.data.setdefault(DOMAIN, {})

    config = entry.data
    options = entry.options

    session = async_get_clientsession(hass, False)

    specific_devices_types = []
    if any(d[CONF_TYPE] == TYPE_COUNTER for d in config[CONF_DEVICES]):
        specific_devices_types.append(TYPE_COUNTER)

    ipx = IPX800(
        host=config[CONF_HOST],
        port=config[CONF_PORT],
        api_key=config[CONF_API_KEY],
        username=config.get(CONF_USERNAME),
        password=config.get(CONF_PASSWORD),
        specific_devices_types=specific_devices_types,
        session=session,
    )

    try:
        if not await ipx.ping():
            raise Ipx800CannotConnectError()
    except Ipx800CannotConnectError as exception:
        _LOGGER.error(
            "Cannot connect to the IPX800 named %s, check host, port or api_key",
            config[CONF_NAME],
        )
        raise ConfigEntryNotReady from exception

    async def async_update_data():
        """Fetch data from API."""
        try:
            return await ipx.global_get()
        except Ipx800InvalidAuthError as err:
            raise UpdateFailed("Authentication error on IPX800") from err
        except Ipx800CannotConnectError as err:
            raise UpdateFailed(f"Failed to communicating with API: {err}") from err

    scan_interval = options.get(
        CONF_SCAN_INTERVAL, config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    if scan_interval < 10:
        _LOGGER.warning(
            "A scan interval too low has been set, you probably will get errors since the IPX800 can't handle too much request at the same time"
        )

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=scan_interval),
        request_refresh_debouncer=Debouncer(
            hass,
            _LOGGER,
            cooldown=REQUEST_REFRESH_DELAY,
            immediate=False,
        ),
    )

    undo_listener = entry.add_update_listener(_async_update_listener)

    await coordinator.async_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        CONF_NAME: config[CONF_NAME],
        CONTROLLER: ipx,
        COORDINATOR: coordinator,
        CONF_DEVICES: {},
        UNDO_UPDATE_LISTENER: undo_listener,
    }

    # Create the IPX800 device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, ipx.host)},
        manufacturer="GCE",
        model="IPX800 V4",
        name=config[CONF_NAME],
        configuration_url=f"http://{config[CONF_HOST]}:{config[CONF_PORT]}",
    )

    if CONF_DEVICES not in config:
        _LOGGER.warning(
            "No devices configuration found for the IPX800 %s", config[CONF_NAME]
        )
        return True

    # Load each supported component entities from their devices
    devices = build_device_list(config[CONF_DEVICES])

    for component in CONF_COMPONENT_ALLOWED:
        _LOGGER.debug("Load component %s", component)
        hass.data[DOMAIN][entry.entry_id][CONF_DEVICES][component] = filter_device_list(
            devices, component
        )
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    # Provide endpoints for the IPX to call to push states
    if CONF_PUSH_PASSWORD in config:
        hass.http.register_view(
            IpxRequestView(config[CONF_HOST], config[CONF_PUSH_PASSWORD])
        )
        hass.http.register_view(
            IpxRequestDataView(config[CONF_HOST], config[CONF_PUSH_PASSWORD])
        )
        hass.http.register_view(
            IpxRequestRefreshView(
                config[CONF_HOST], config[CONF_PUSH_PASSWORD], coordinator
            )
        )
    else:
        _LOGGER.info(
            "No %s parameter provided in configuration, skip API call handling for IPX800 PUSH",
            CONF_PUSH_PASSWORD,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    for component in CONF_COMPONENT_ALLOWED:
        await hass.config_entries.async_forward_entry_unload(entry, component)

    del hass.data[DOMAIN]

    return True


async def _async_update_listener(hass, config_entry):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


def build_device_list(devices_config: list) -> list:
    """Check and build device list from config."""
    _LOGGER.debug("Check and build devices configuration")

    devices = []
    for device_config in devices_config:
        _LOGGER.debug("Read device name: %s", device_config.get(CONF_NAME))

        # Check if component is supported
        if device_config[CONF_COMPONENT] not in CONF_COMPONENT_ALLOWED:
            _LOGGER.error(
                "Device %s skipped: %s %s not correct or supported",
                device_config[CONF_NAME],
                CONF_COMPONENT,
                device_config[CONF_COMPONENT],
            )
            continue

        # Check if type is supported
        if device_config[CONF_TYPE] not in CONF_TYPE_ALLOWED:
            _LOGGER.error(
                "Device %s skipped: %s %s not correct or supported",
                device_config[CONF_NAME],
                CONF_TYPE,
                device_config[CONF_TYPE],
            )
            continue

        # Check if X4VR have extension id set
        if (
            device_config[CONF_TYPE] == TYPE_X4VR
            or device_config[CONF_TYPE] == TYPE_X4VR_BSO
        ) and CONF_EXT_ID not in device_config:
            _LOGGER.error(
                "Device %s skipped: %s must have %s set",
                device_config[CONF_NAME],
                TYPE_X4VR,
                CONF_EXT_ID,
            )
            continue

        # Check if only PWM have default_brightness set
        if CONF_DEFAULT_BRIGHTNESS in device_config and not (
            device_config[CONF_TYPE] == TYPE_XPWM
            or device_config[CONF_TYPE] == TYPE_XPWM_RGB
            or device_config[CONF_TYPE] == TYPE_XPWM_RGBW
        ):
            _LOGGER.error(
                "Device %s skipped: %s must be set only for XPWM types",
                device_config[CONF_NAME],
                CONF_DEFAULT_BRIGHTNESS,
            )
            continue

        # Check if only PWM have default_brightness set
        if CONF_DEFAULT_BRIGHTNESS in device_config and (
            device_config[CONF_DEFAULT_BRIGHTNESS] < 1
            or device_config[CONF_DEFAULT_BRIGHTNESS] > 255
        ):
            _LOGGER.error(
                "Device %s skipped: %s must be between 1 and 255",
                device_config[CONF_NAME],
                CONF_DEFAULT_BRIGHTNESS,
            )
            continue

        # Check if RGB/RBW or FP/RELAY have ids set
        if (
            device_config[CONF_TYPE] == TYPE_XPWM_RGB
            or device_config[CONF_TYPE] == TYPE_XPWM_RGBW
            or (
                device_config[CONF_TYPE] == TYPE_RELAY
                and device_config[CONF_COMPONENT] == "climate"
            )
        ) and CONF_IDS not in device_config:
            _LOGGER.error(
                "Device %s skipped: RGB/RGBW must have %s set",
                device_config[CONF_NAME],
                CONF_IDS,
            )
            continue

        # Check if other device types have id set
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
                "Device %s skipped: must have %s set",
                device_config[CONF_NAME],
                CONF_ID,
            )
            continue

        devices.append(device_config)
        _LOGGER.info(
            "Device %s added (component: %s)",
            device_config[CONF_NAME],
            device_config[CONF_COMPONENT],
        )
    return devices


def filter_device_list(devices: list, component: str) -> list:
    """Filter device list by component."""
    return list(filter(lambda d: d[CONF_COMPONENT] == component, devices))


def check_api_auth(request, host, password) -> bool:
    """Check authentication on API call."""
    if request.remote != host:
        raise ApiCallNotAuthorized("API call not coming from IPX800 IP.")
    if "Authorization" not in request.headers:
        raise ApiCallNotAuthorized("API call no authentication provided.")
    header_auth = request.headers["Authorization"]
    split = header_auth.strip().split(" ")
    if len(split) != 2 or split[0].strip().lower() != "basic":
        raise ApiCallNotAuthorized("Malformed Authorization header")
    header_username, header_password = b64decode(split[1]).decode().split(":", 1)
    if header_username != PUSH_USERNAME or header_password != password:
        raise ApiCallNotAuthorized("API call authentication invalid.")
    return True


class IpxRequestView(HomeAssistantView):
    """Provide a page for the device to call."""

    requires_auth = False
    url = "/api/ipx800v4/{entity_id}/{state}"
    name = "api:ipx800v4"

    def __init__(self, host: str, password: str) -> None:
        """Init the IPX view."""
        self.host = host
        self.password = password
        super().__init__()

    async def get(self, request, entity_id, state):
        """Respond to requests from the device."""
        if check_api_auth(request, self.host, self.password):
            hass = request.app["hass"]
            old_state = hass.states.get(entity_id)
            _LOGGER.debug("Update %s to state %s", entity_id, state)
            if old_state:
                hass.states.async_set(entity_id, state, old_state.attributes)
                return web.Response(status=HTTPStatus.OK, text="OK")
            _LOGGER.warning("Entity not found for state updating: %s", entity_id)


class IpxRequestDataView(HomeAssistantView):
    """Provide a page for the device to call for send multiple data at once."""

    requires_auth = False
    url = "/api/ipx800v4_data/{data}"
    name = "api:ipx800v4_data"

    def __init__(self, host: str, password: str) -> None:
        """Init the IPX view."""
        self.host = host
        self.password = password
        super().__init__()

    async def get(self, request, data):
        """Respond to requests from the device."""
        if check_api_auth(request, self.host, self.password):
            hass = request.app["hass"]
            entities_data = data.split("&")
            for entity_data in entities_data:
                entity_id = entity_data.split("=")[0]
                state = (
                    "on" if entity_data.split("=")[1] in ["1", "on", "true"] else "off"
                )

                old_state = hass.states.get(entity_id)
                _LOGGER.debug("Update %s to state %s", entity_id, state)
                if old_state:
                    hass.states.async_set(entity_id, state, old_state.attributes)
                else:
                    _LOGGER.warning(
                        "Entity not found for state updating: %s", entity_id
                    )

            return web.Response(status=HTTPStatus.OK, text="OK")


class IpxRequestRefreshView(HomeAssistantView):
    """Provide a page for the device to call for send multiple data at once."""

    requires_auth = False
    url = "/api/ipx800v4_refresh"
    name = "api:ipx800v4_refresh"

    def __init__(
        self, host: str, password: str, coordinator: DataUpdateCoordinator
    ) -> None:
        """Init the IPX view."""
        self.host = host
        self.password = password
        self.coordinator = coordinator
        super().__init__()

    async def get(self, request, data):
        """Respond to requests from the device."""
        if check_api_auth(request, self.host, self.password):
            self.coordinator.async_request_refresh()
            return web.Response(status=HTTPStatus.OK, text="OK")


class ApiCallNotAuthorized(BaseException):
    """API call for IPX800 view not authorized."""


class IpxEntity(CoordinatorEntity):
    """Representation of a IPX800 generic device entity."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
        suffix_name: str = "",
    ) -> None:
        """Initialize the device."""
        super().__init__(coordinator)

        self.ipx = ipx
        self._transition = int(
            device_config.get(CONF_TRANSITION, DEFAULT_TRANSITION) * 1000
        )
        self._ipx_type = device_config[CONF_TYPE]
        self._component = device_config[CONF_COMPONENT]
        self._id = device_config.get(CONF_ID)
        self._ext_id = device_config.get(CONF_EXT_ID)
        self._ids = device_config.get(CONF_IDS, [])

        self._attr_name: str = device_config[CONF_NAME]
        if suffix_name:
            self._attr_name = f"{self._attr_name} {suffix_name}"
        self._attr_device_class = device_config.get(CONF_DEVICE_CLASS)
        self._attr_native_unit_of_measurement = device_config.get(
            CONF_UNIT_OF_MEASUREMENT
        )
        self._attr_icon = device_config.get(CONF_ICON)
        self._attr_unique_id = "_".join(
            [DOMAIN, self.ipx.host, self._component, slugify(self._attr_name)]
        )

        configuration_url = f"http://{self.ipx.host}:{self.ipx.port}/admin/"
        if self._ipx_type == TYPE_RELAY:
            if self._id:
                if self._id <= 8:
                    configuration_url += "output.htm"
                else:
                    configuration_url += "8out.htm"
        elif self._ipx_type in [TYPE_X4VR, TYPE_X4VR_BSO]:
            configuration_url += "volet.htm"
        elif self._ipx_type in [TYPE_XPWM, TYPE_XPWM_RGB, TYPE_XPWM_RGBW]:
            configuration_url += "pwm.htm"
        elif self._ipx_type == TYPE_XDIMMER:
            configuration_url += "dimmer.htm"
        elif self._ipx_type == TYPE_VIRTUALOUT:
            configuration_url += "virtualout.htm"
        elif self._ipx_type == TYPE_VIRTUALIN:
            configuration_url += "virtualin.htm"
        elif self._ipx_type == TYPE_ANALOGIN:
            configuration_url += "analog.htm"
        elif self._ipx_type == TYPE_VIRTUALANALOGIN:
            configuration_url += "analogVirt.htm"
        elif self._ipx_type == TYPE_DIGITALIN:
            if self._id:
                if self._id <= 8:
                    configuration_url += "input.htm"
                else:
                    configuration_url += "24in.htm"
        elif self._ipx_type == TYPE_XTHL:
            configuration_url += "rht.htm"
        else:
            configuration_url += "periph.htm"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, slugify(device_config[CONF_NAME]))},
            "name": device_config[CONF_NAME],
            "manufacturer": "GCE",
            "model": "IPX800 V4",
            "via_device": (DOMAIN, self.ipx.host),
            "configuration_url": configuration_url,
        }
