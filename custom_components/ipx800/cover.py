"""Support for IPX800 cover."""
import logging

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.components.cover import (
    CoverEntity,
    SUPPORT_OPEN,
    SUPPORT_CLOSE,
    SUPPORT_SET_POSITION,
    ATTR_POSITION,
    DEVICE_CLASS_SHUTTER,
)

from pypx800 import *
from .device import *
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the IPX800 cover."""
    async_add_entities(
        [
            X4VRCover(device)
            for device in (
                item
                for item in discovery_info
                if item.get("config").get(CONF_TYPE) == TYPE_X4VR
            )
        ],
        True,
    )


class X4VRCover(IpxDevice, CoverEntity):
    """Representation of a IPX Switch through relay."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.control = VR(self.controller.ipx, self._ext_id, self._id)
        self._supported_features |= SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_SET_POSITION

    @property
    def device_class(self):
        return self._device_class or DEVICE_CLASS_SHUTTER

    @property
    def is_closed(self) -> bool:
        return int(self.coordinator.data[f"VR{self._ext_id}-{self._id}"]) == 100

    @property
    def current_cover_position(self) -> int:
        return 100 - int(self.coordinator.data[f"VR{self._ext_id}-{self._id}"])

    def open_cover(self, **kwargs):
        """Open the cover."""
        self.control.on()

    def close_cover(self, **kwargs):
        """Close cover."""
        self.control.off()

    def set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        self.control.set_level(100-kwargs.get(ATTR_POSITION))
