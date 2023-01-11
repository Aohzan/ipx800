"""Support for IPX800 V4 covers."""
import logging

from pypx800 import IPX800, X4VR, Ipx800RequestError

from homeassistant.components.cover import (
    ATTR_POSITION,
    DEVICE_CLASS_SHUTTER,
    SUPPORT_CLOSE,
    SUPPORT_CLOSE_TILT,
    SUPPORT_OPEN,
    SUPPORT_OPEN_TILT,
    SUPPORT_SET_POSITION,
    SUPPORT_STOP,
    CoverEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import IpxEntity
from .const import (
    CONF_DEVICES,
    CONF_TYPE,
    CONTROLLER,
    COORDINATOR,
    DOMAIN,
    GLOBAL_PARALLEL_UPDATES,
    TYPE_X4VR_BSO,
)

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IPX800 covers."""
    controller = hass.data[DOMAIN][entry.entry_id][CONTROLLER]
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    devices = hass.data[DOMAIN][entry.entry_id][CONF_DEVICES]["cover"]

    entities: list[CoverEntity] = []

    for device in devices:
        entities.append(X4VRCover(device, controller, coordinator))

    async_add_entities(entities, True)


class X4VRCover(IpxEntity, CoverEntity):
    """Representation of a IPX Cover through X4VR."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the X4VRCover."""
        super().__init__(device_config, ipx, coordinator)
        self.control = X4VR(ipx, self._ext_id, self._id)
        self._attr_device_class = DEVICE_CLASS_SHUTTER
        self._attr_supported_features = (
            SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_STOP | SUPPORT_SET_POSITION
        )
        if device_config[CONF_TYPE] == TYPE_X4VR_BSO:
            self._attr_supported_features += SUPPORT_CLOSE_TILT | SUPPORT_OPEN_TILT

    @property
    def is_closed(self) -> bool:
        """Return the state."""
        if value := self.coordinator.data.get(f"VR{self._ext_id}-{self._id}") is not None:
            return value == 100
        return None

    @property
    def current_cover_position(self) -> int:
        """Return the current cover position."""
        if value := self.coordinator.data.get(f"VR{self._ext_id}-{self._id}") is not None:
            return 100 - int(value)

    async def async_open_cover(self, **kwargs) -> None:
        """Open cover."""
        try:
            await self.control.on()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while open IPX800 cover: %s", self.name)

    async def async_close_cover(self, **kwargs) -> None:
        """Close cover."""
        try:
            await self.control.off()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while close IPX800 cover: %s", self.name)

    async def async_stop_cover(self, **kwargs) -> None:
        """Stop the cover."""
        try:
            await self.control.stop()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while stop IPX800 cover: %s", self.name)

    async def async_set_cover_position(self, **kwargs) -> None:
        """Set the cover to a specific position."""
        try:
            await self.control.set_level(kwargs.get(ATTR_POSITION))
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while set IPX800 cover position: %s", self.name
            )

    async def async_open_cover_tilt(self, **kwargs):
        """Open the cover tilt."""
        try:
            await self.control.set_pulse_up(1)
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while set IPX800 tilt position: %s", self.name
            )

    async def async_close_cover_tilt(self, **kwargs):
        """Close the cover tilt."""
        try:
            await self.control.set_pulse_down(1)
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while set IPX800 cover position: %s", self.name
            )
