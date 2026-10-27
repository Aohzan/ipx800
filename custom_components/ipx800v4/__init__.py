"""Support for the GCE IPX800 V4."""

from datetime import timedelta
from functools import partial
import logging
from typing import TypedDict

from aiohttp import ClientSession
import probatio
from pypx800 import IPX800

from homeassistant.config_entries import SOURCE_IMPORT
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.typing import ConfigType

from .commands import IpxCommandClient
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
    CONF_RETRY_COMMANDS,
    CONF_TRANSITION,
    CONF_TYPE,
    CONF_TYPE_ALLOWED,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRANSITION,
    DOMAIN,
    PLATFORMS,
    REQUEST_REFRESH_DELAY,
    TYPE_COUNTER,
    TYPE_RELAY,
    TYPE_VIRTUALANALOGIN,
    TYPE_X4VR,
    TYPE_X4VR_BSO,
    TYPE_XPWM,
    TYPE_XPWM_RGB,
    TYPE_XPWM_RGBW,
)
from .coordinator import (
    PUSH_ENTRIES,
    IpxConfigEntry,
    IpxData,
    IpxDataUpdateCoordinator,
    IpxSystemCoordinator,
    auth_issue_id,
)
from .push import (
    IpxRequestBulkUpdateView,
    IpxRequestDataView,
    IpxRequestRefreshView,
    IpxRequestView,
)
from .system import IpxSystemData

_LOGGER = logging.getLogger(__name__)

DEVICE_CONFIG_SCHEMA_ENTRY = probatio.Schema(
    {
        probatio.Optional(CONF_RETRY_COMMANDS, default=True): cv.boolean,
        probatio.Required(CONF_NAME): cv.string,
        probatio.Required(CONF_COMPONENT): cv.string,
        probatio.Required(CONF_TYPE): cv.string,
        probatio.Optional(CONF_ID): cv.positive_int,
        probatio.Optional(CONF_IDS): cv.ensure_list,
        probatio.Optional(CONF_INVERT_VALUE, default=False): cv.boolean,
        probatio.Optional(CONF_EXT_ID): cv.positive_int,
        probatio.Optional(CONF_DEFAULT_BRIGHTNESS): cv.positive_int,
        probatio.Optional(CONF_ICON): cv.icon,
        probatio.Optional(CONF_TRANSITION, default=DEFAULT_TRANSITION): probatio.Coerce(
            float
        ),
        probatio.Optional(CONF_DEVICE_CLASS): cv.string,
        probatio.Optional(CONF_UNIT_OF_MEASUREMENT): cv.string,
    }
)

GATEWAY_CONFIG = probatio.Schema(
    {
        probatio.Required(CONF_NAME): cv.string,
        probatio.Required(CONF_HOST): cv.string,
        probatio.Optional(CONF_PORT, default=80): cv.port,
        probatio.Required(CONF_API_KEY): cv.string,
        probatio.Optional(CONF_USERNAME): cv.string,
        probatio.Optional(CONF_PASSWORD): cv.string,
        probatio.Optional(CONF_SCAN_INTERVAL): probatio.All(
            probatio.Coerce(int), probatio.Range(min=1)
        ),
        probatio.Optional(CONF_PUSH_PASSWORD): cv.string,
        probatio.Optional(CONF_PUSH_CHECK_HOST, default=True): cv.boolean,
        probatio.Optional(CONF_DEVICES, default=[]): probatio.All(
            cv.ensure_list, [DEVICE_CONFIG_SCHEMA_ENTRY]
        ),
    },
    extra=probatio.ALLOW_EXTRA,
)

CONFIG_SCHEMA = probatio.Schema(
    {DOMAIN: probatio.All(cv.ensure_list, [GATEWAY_CONFIG])},
    extra=probatio.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the IPX800 from config file."""
    hass.data.setdefault(PUSH_ENTRIES, {})
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


class IpxClientOptions(TypedDict):
    """Arguments shared by the polling and the command pypx800 clients."""

    host: str
    port: int
    api_key: str
    username: str | None
    password: str | None
    specific_devices_types: list[str]
    session: ClientSession


async def async_setup_entry(hass: HomeAssistant, entry: IpxConfigEntry) -> bool:
    """Set up the IPX800v4."""
    config = entry.data
    options = entry.options

    session = async_get_clientsession(hass, False)

    # pypx800 polls these types with a separate request, only when configured
    specific_devices_types = [
        device_type
        for device_type in (TYPE_COUNTER, TYPE_VIRTUALANALOGIN)
        if any(d[CONF_TYPE] == device_type for d in config[CONF_DEVICES])
    ]

    # pypx800 reads and sets X-PWM levels (PWMx fields) only with web credentials
    if not (config.get(CONF_USERNAME) and config.get(CONF_PASSWORD)) and any(
        d[CONF_TYPE] in (TYPE_XPWM, TYPE_XPWM_RGB, TYPE_XPWM_RGBW)
        for d in config[CONF_DEVICES]
    ):
        _LOGGER.warning(
            "X-PWM devices of the IPX800 %s stay unavailable: set %s and %s",
            config[CONF_NAME],
            CONF_USERNAME,
            CONF_PASSWORD,
        )

    client_options = IpxClientOptions(
        host=config[CONF_HOST],
        port=config[CONF_PORT],
        api_key=config[CONF_API_KEY],
        username=config.get(CONF_USERNAME),
        password=config.get(CONF_PASSWORD),
        specific_devices_types=specific_devices_types,
        session=session,
    )
    ipx = IPX800(**client_options)
    # Share HA's session; replay policy is explicit at each command call site.
    # The polling client retains its existing request/recovery behavior.
    command_ipx = IpxCommandClient(**client_options, request_retries=1)

    system = IpxSystemData(
        session,
        config[CONF_HOST],
        config[CONF_PORT],
        config.get(CONF_USERNAME),
        config.get(CONF_PASSWORD),
    )
    controller_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, ipx.host)},
        manufacturer="GCE",
        model="IPX800 V4",
        name=config[CONF_NAME],
        configuration_url=f"http://{config[CONF_HOST]}:{config[CONF_PORT]}",
    )

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
        controller_device_id=controller_device.id,
        name=f"{config[CONF_NAME]} ({config[CONF_HOST]})",
        update_method=ipx.global_get,
        update_interval=timedelta(seconds=scan_interval),
        request_refresh_debouncer=Debouncer(
            hass,
            _LOGGER,
            cooldown=REQUEST_REFRESH_DELAY,
            immediate=False,
        ),
    )

    await coordinator.async_config_entry_first_refresh()

    system_coordinator = IpxSystemCoordinator(
        hass,
        entry,
        system,
        controller_device.id,
        timedelta(seconds=scan_interval),
    )
    # Initial snapshot, then timer-only polling. A failed diagnostics read
    # doesn't prevent the setup.
    await system_coordinator.async_refresh()

    # Load each supported component entities from their devices
    devices = build_device_list(config[CONF_DEVICES])
    entry_data = entry.runtime_data = IpxData(
        name=config[CONF_NAME],
        controller=command_ipx,
        coordinator=coordinator,
        system_coordinator=system_coordinator,
        devices={
            component: filter_device_list(devices, component) for component in PLATFORMS
        },
    )
    hass.data.setdefault(PUSH_ENTRIES, {})[entry.entry_id] = entry_data
    entry.async_on_unload(
        partial(_async_remove_entry_data, hass, entry.entry_id, entry_data)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Expose push access only once this entry and its platforms are ready.
    if CONF_PUSH_PASSWORD in config:
        entry_data.push_config = dict(config)
    else:
        _LOGGER.info(
            "No %s parameter provided in configuration, skip API call handling for IPX800 PUSH",
            CONF_PUSH_PASSWORD,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: IpxConfigEntry) -> bool:
    """Unload a config entry, the coordinators are shut down with it."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    _async_remove_entry_data(hass, entry.entry_id, entry.runtime_data)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: IpxConfigEntry) -> None:
    """Remove the repair issue of a removed entry."""
    ir.async_delete_issue(hass, DOMAIN, auth_issue_id(entry.entry_id))


@callback
def _async_remove_entry_data(
    hass: HomeAssistant, entry_id: str, entry_data: IpxData
) -> None:
    """Detach this runtime, including after incomplete setup; keep newer entries."""
    entries = hass.data.get(PUSH_ENTRIES, {})
    if entries.get(entry_id) is entry_data:
        entries.pop(entry_id)
    # Keep the domain container: pending setups and stateless routes can reuse it.


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: IpxConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow removing a device left without entities."""
    return not er.async_entries_for_device(
        er.async_get(hass), device_entry.id, include_disabled_entities=True
    )


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
