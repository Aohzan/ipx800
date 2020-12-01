"""Support for IPX800 cover."""
import logging

from homeassistant.components.cover import (ATTR_POSITION,
                                            DEVICE_CLASS_SHUTTER,
                                            SUPPORT_CLOSE, SUPPORT_OPEN,
                                            SUPPORT_SET_POSITION, SUPPORT_STOP,
                                            CoverEntity)
from homeassistant.exceptions import ConfigEntryNotReady
from pypx800 import *

from . import IpxController, IpxDevice
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the IPX800 cover."""
    controller = hass.data[DOMAIN][discovery_info[CONTROLLER]]

    async_add_entities(
        [
            X4VRCover(device, controller)
            for device in (
                item
                for item in discovery_info[CONF_DEVICES]
                if item.get(CONF_TYPE) == TYPE_X4VR
            )
        ],
        True,
    )


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

    def open_cover(self, **kwargs):
        """Open the cover."""
        self.control.on()

    def close_cover(self, **kwargs):
        """Close cover."""
        self.control.off()

    def stop_cover(self, **kwargs):
        """Stop the cover."""
        self.control.stop()

    def set_cover_position(self, **kwargs):
        """Set the cover to a specific position."""
        self.control.set_level(kwargs.get(ATTR_POSITION))
