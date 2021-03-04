"""Support for IPX800 cover."""
import logging

from pypx800 import *

from homeassistant.components.cover import (
    ATTR_POSITION,
    DEVICE_CLASS_SHUTTER,
    SUPPORT_CLOSE,
    SUPPORT_OPEN,
    SUPPORT_SET_POSITION,
    SUPPORT_STOP,
    CoverEntity,
)

from . import IpxController, IpxDevice
from .const import *

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Set up the IPX800 covers."""
    controller = hass.data[DOMAIN][config_entry.entry_id][CONTROLLER]
    devices = filter(
        lambda d: d[CONF_COMPONENT] == "cover", config_entry.data[CONF_DEVICES]
    )

    entities = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_X4VR:
            entities.append(X4VRCover(device, controller))

    async_add_entities(entities, True)


class X4VRCover(IpxDevice, CoverEntity):
    """Representation of a IPX Cover through X4VR."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.control = X4VR(controller.ipx, self._ext_id, self._id)
        self._supported_features |= (
            SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_STOP | SUPPORT_SET_POSITION
        )

    @property
    def device_class(self):
        return self._device_class or DEVICE_CLASS_SHUTTER

    @property
    def is_closed(self) -> bool:
        return int(self.coordinator.data[f"VR{self._ext_id}-{self._id}"]) == 100

    @property
    def current_cover_position(self) -> int:
        return 100 - int(self.coordinator.data[f"VR{self._ext_id}-{self._id}"])

    async def async_open_cover(self, **kwargs):
        """Open cover."""
        self.control.on()

    async def async_close_cover(self, **kwargs):
        """Close cover."""
        self.control.off()

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        self.control.stop()

    def set_cover_position(self, **kwargs):
        """Set the cover to a specific position."""
        self.control.set_level(kwargs.get(ATTR_POSITION))
