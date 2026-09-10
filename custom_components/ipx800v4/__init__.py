"""Support for the GCE IPX800 V4."""

from datetime import timedelta
from functools import partial
import logging

from pypx800 import IPX800
import voluptuous as vol

from homeassistant.helpers.device_registry import DeviceEntry
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_COMPONENT,
    CONF_DEFAULT_BRIGHTNESS,
    CONF_DEVICES,
    CONF_EXT_ID,
    CONF_ID,
    CONF_IDS,
    CONF_INVERT_VALUE,
    CONF_PUSH_CHECK_HOST,
    CONF_PUSH_PASSWORD,
    CONF_TRANSITION,
    CONF_TYPE,
    CONF_TYPE_ALLOWED,
    CONTROLLER,
    COORDINATOR,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRANSITION,
    DOMAIN,
    PUSH_CONFIG,
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

from .coordinator import IpxDataUpdateCoordinator
from .push import (
    IpxRequestView,
    IpxRequestDataView,
    IpxRequestBulkUpdateView,
    IpxRequestRefreshView,
)
from .system import IpxSystemData

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
        vol.Optional(CONF_PUSH_PASSWORD): cv.string,
        vol.Optional(CONF_PUSH_CHECK_HOST, default=True): cv.boolean,
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
    # Integration setup runs once. Routes resolve live entries on every request.
    for view in (
        IpxRequestView,
        IpxRequestDataView,
        IpxRequestBulkUpdateView,
        IpxRequestRefreshView,
    ):
        hass.http.register_view(view())

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

    client_options = {
        "host": config[CONF_HOST],
        "port": config[CONF_PORT],
        "api_key": config[CONF_API_KEY],
        "username": config.get(CONF_USERNAME),
        "password": config.get(CONF_PASSWORD),
        "specific_devices_types": specific_devices_types,
        "session": session,
    }
    ipx = IPX800(**client_options)
    # Share HA's session, but never replay writes after an ambiguous response.
    # The polling client retains its existing request/recovery behavior.
    command_ipx = IPX800(**client_options, request_retries=1)

    system = IpxSystemData(
        session,
        config[CONF_HOST],
        config[CONF_PORT],
        config.get(CONF_USERNAME),
        config.get(CONF_PASSWORD),
    )
    device_registry = dr.async_get(hass)
    controller_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, ipx.host)},
        manufacturer="GCE",
        model="IPX800 V4",
        name=config[CONF_NAME],
        configuration_url=f"http://{config[CONF_HOST]}:{config[CONF_PORT]}",
    )
    controller_mac = None

    async def async_update_data():
        """Fetch data from API."""
        nonlocal controller_mac
        data = await ipx.global_get()

        # Sequential requests share the configured scan interval and debouncer.
        data["system"] = await system.async_get()
        if (mac := data["system"].get("mac")) and mac != controller_mac:
            device_registry.async_update_device(
                controller_device.id,
                merge_connections={(dr.CONNECTION_NETWORK_MAC, mac)},
            )
            controller_mac = mac
        return data

    scan_interval = options.get(
        CONF_SCAN_INTERVAL, config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    if scan_interval < 10:
        _LOGGER.warning(
            "A scan interval too low has been set, you probably will get errors since the IPX800 can't handle too much request at the same time"
        )

    coordinator = IpxDataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=f"{config[CONF_NAME]} ({config[CONF_HOST]})",
        update_method=async_update_data,
        update_interval=timedelta(seconds=scan_interval),
        request_refresh_debouncer=Debouncer(
            hass,
            _LOGGER,
            cooldown=REQUEST_REFRESH_DELAY,
            immediate=False,
        ),
    )

    await coordinator.async_config_entry_first_refresh()

    undo_listener = entry.add_update_listener(_async_update_listener)
    entry.async_on_unload(undo_listener)

    entry_data = hass.data[DOMAIN][entry.entry_id] = {
        CONF_NAME: config[CONF_NAME],
        CONTROLLER: command_ipx,
        COORDINATOR: coordinator,
        CONF_DEVICES: {},
        UNDO_UPDATE_LISTENER: undo_listener,
    }
    entry.async_on_unload(
        partial(_async_remove_entry_data, hass, entry.entry_id, entry_data)
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

    # Expose push access only once this entry and its platforms are ready.
    if CONF_PUSH_PASSWORD in config:
        entry_data[PUSH_CONFIG] = config
    else:
        _LOGGER.info(
            "No %s parameter provided in configuration, skip API call handling for IPX800 PUSH",
            CONF_PUSH_PASSWORD,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entry_data is not None:
        _async_remove_entry_data(hass, entry.entry_id, entry_data)
        await entry_data[COORDINATOR].async_shutdown()
    return True


@callback
def _async_remove_entry_data(hass: HomeAssistant, entry_id: str, entry_data: dict) -> None:
    """Detach this runtime, including after incomplete setup; keep newer entries."""
    entries = hass.data.get(DOMAIN, {})
    if entries.get(entry_id) is entry_data:
        entries.pop(entry_id)
    # Keep the domain container: pending setups and stateless routes can reuse it.


async def _async_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Remove a config entry from a device."""
    entity_registry = er.async_get(hass)
    entities = er.async_entries_for_device(entity_registry, device_entry.id)
    if entities:
        return False

    device_registry = dr.async_get(hass)
    device_registry.async_remove_device(device_entry.id)
    return True


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
