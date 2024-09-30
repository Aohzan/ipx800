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
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import slugify

from .const import (
    CONF_COMPONENT,
    CONF_DEFAULT_BRIGHTNESS,
    CONF_DEVICES,
    CONF_EXT_ID,
    CONF_ID,
    CONF_IDS,
    CONF_INVERT_VALUE,
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
    TYPE_COUNTER,
    TYPE_RELAY,
    TYPE_X4VR,
    TYPE_X4VR_BSO,
    TYPE_XPWM,
    TYPE_XPWM_RGB,
    TYPE_XPWM_RGBW,
    UNDO_UPDATE_LISTENER,
)

_LOGGER = logging.getLogger(__name__)


PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

DEVICE_CONFIG_SCHEMA_ENTRY = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_COMPONENT): cv.string,
        vol.Required(CONF_TYPE): cv.string,
        vol.Optional(CONF_ID): cv.positive_int,
        vol.Optional(CONF_IDS): cv.ensure_list,
        vol.Optional(CONF_INVERT_VALUE, default=False): cv.boolean,
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

    async def check_connection():
        if not await ipx.ping():
            raise Ipx800CannotConnectError

    try:
        await check_connection()
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

    for component in PLATFORMS:
        _LOGGER.debug("Load component %s", component)
        hass.data[DOMAIN][entry.entry_id][CONF_DEVICES][component] = filter_device_list(
            devices, component
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Provide endpoints for the IPX to call to push states
    if CONF_PUSH_PASSWORD in config:
        hass.http.register_view(
            IpxRequestView(
                config[CONF_NAME], config[CONF_HOST], config[CONF_PUSH_PASSWORD]
            )
        )
        hass.http.register_view(
            IpxRequestDataView(
                config[CONF_NAME], config[CONF_HOST], config[CONF_PUSH_PASSWORD]
            )
        )
        hass.http.register_view(
            IpxRequestBulkUpdateView(
                config[CONF_NAME],
                config[CONF_HOST],
                config[CONF_PUSH_PASSWORD],
                devices,
            )
        )
        hass.http.register_view(
            IpxRequestRefreshView(
                config[CONF_NAME],
                config[CONF_HOST],
                config[CONF_PUSH_PASSWORD],
                coordinator,
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
    for component in PLATFORMS:
        await hass.config_entries.async_forward_entry_unload(entry, component)

    del hass.data[DOMAIN]

    return True


async def _async_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


def build_device_list(devices_config: list) -> list:
    """Check and build device list from config."""
    _LOGGER.debug("Check and build devices configuration")

    devices = []
    for device_config in devices_config:
        _LOGGER.debug("Read device name: %s", device_config.get(CONF_NAME))

        # Check if component is supported
        if device_config[CONF_COMPONENT] not in PLATFORMS:
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
        _LOGGER.warning("API call not coming from IPX800 IP")
        return False
    if "Authorization" not in request.headers:
        _LOGGER.warning("API call no authentication provided")
        return False
    header_auth = request.headers["Authorization"]
    split = header_auth.strip().split(" ")
    if len(split) != 2 or split[0].strip().lower() != "basic":
        _LOGGER.warning("Malformed Authorization header")
        return False
    header_username, header_password = b64decode(split[1]).decode().split(":", 1)
    if header_username != PUSH_USERNAME or header_password != password:
        _LOGGER.warning("API call authentication invalid")
        return False
    return True


class IpxRequestView(HomeAssistantView):
    """Provide a page for the device to call."""

    requires_auth = False
    url = "/api/ipx800v4/{entity_id}/{state}"
    name = "api:ipx800v4"

    def __init__(self, name: str, host: str, password: str) -> None:
        """Init the IPX view."""
        self.extra_urls = [f"/api/ipx800v4/{name}/{{entity_id}}/{{state}}"]
        self.host = host
        self.password = password
        super().__init__()

    async def get(self, request, entity_id, state):
        """Respond to requests from the device."""
        if not check_api_auth(request, self.host, self.password):
            return web.Response(status=HTTPStatus.UNAUTHORIZED, text="Unauthorized")
        hass = request.app["hass"]
        old_state = hass.states.get(entity_id)
        _LOGGER.debug("Update %s to state %s", entity_id, state)
        if old_state:
            hass.states.async_set(entity_id, state, old_state.attributes)
            return web.Response(status=HTTPStatus.OK, text="OK")
        _LOGGER.warning("Entity not found for state updating: %s", entity_id)
        return None


class IpxRequestDataView(HomeAssistantView):
    """Provide a page for the device to call for send multiple data at once."""

    requires_auth = False
    url = "/api/ipx800v4_data/{data}"
    name = "api:ipx800v4_data"

    def __init__(self, name: str, host: str, password: str) -> None:
        """Init the IPX view."""
        self.host = host
        self.password = password
        super().__init__()

    async def get(self, request, data):
        """Respond to requests from the device."""
        if not check_api_auth(request, self.host, self.password):
            return web.Response(status=HTTPStatus.UNAUTHORIZED, text="Unauthorized")
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


class IpxRequestBulkUpdateView(HomeAssistantView):
    """Provide a page for the device to call for bulk update all states at once."""

    requires_auth = False
    url = "/api/ipx800v4_bulk/{device_type}/{data}"
    name = "api:ipx800v4_bulk"

    def __init__(self, name: str, host: str, password: str, devices: list) -> None:
        """Init the IPX view."""
        self.extra_urls = [f"/api/ipx800v4_bulk/{name}/{{device_type}}/{{data}}"]
        self.host = host
        self.password = password
        self.devices = devices
        super().__init__()

    async def get(self, request, device_type, data):
        """Respond to requests from the device."""
        if not check_api_auth(request, self.host, self.password):
            return web.Response(status=HTTPStatus.UNAUTHORIZED, text="Unauthorized")
        hass = request.app["hass"]
        _LOGGER.debug("Bulk update %s from %s : %s", device_type, self.host, data)
        for device_config in self.devices:
            index = int(device_config[CONF_ID]) - 1
            if device_config[CONF_TYPE] == device_type and 0 <= index < len(data):
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


class IpxRequestRefreshView(HomeAssistantView):
    """Provide a page for the device to force refresh data from coordinator."""

    requires_auth = False
    url = "/api/ipx800v4_refresh/{data}"
    name = "api:ipx800v4_refresh"

    def __init__(
        self, name: str, host: str, password: str, coordinator: DataUpdateCoordinator
    ) -> None:
        """Init the IPX view."""
        self.extra_urls = [f"/api/ipx800v4_refresh/{name}/{{data}}"]
        self.host = host
        self.password = password
        self.coordinator = coordinator
        super().__init__()

    async def get(self, request, data):
        """Respond to requests from the device."""
        if not check_api_auth(request, self.host, self.password):
            return web.Response(status=HTTPStatus.UNAUTHORIZED, text="Unauthorized")
        await self.coordinator.async_request_refresh()
        return web.Response(status=HTTPStatus.OK, text="OK")
