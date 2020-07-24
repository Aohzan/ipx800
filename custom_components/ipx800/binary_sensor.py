"""Support for IPX800 sensors."""
import logging

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity import Entity
from homeassistant.const import STATE_OFF, STATE_ON

from pypx800 import *
from .device import *
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the IPX800 binary_sensors."""

    # add_entities(
    #     [
    #         VirtualOutBinarySensor(device)
    #         for device in (
    #             item
    #             for item in hass.data[IPX800_DEVICES]["binary_sensor"]
    #             if item.get("config").get("virtualout")
    #         )
    #     ],
    #     True,
    # )

    # add_entities(
    #     [
    #         DigitalInBinarySensor(device)
    #         for device in (
    #             item
    #             for item in hass.data[IPX800_DEVICES]["binary_sensor"]
    #             if item.get("config").get("digitalin")
    #         )
    #     ],
    #     True,
    # )


class VirtualOutBinarySensor(IpxDevice, Entity):
    """Representation of a IPX Virtual Out."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.virtualout = self.controller.ipx.virtualout[self.config.get("virtualout")]

    @property
    def device_class(self):
        return self._device_class

    @property
    def is_on(self):
        return bool(self._state)

    @property
    def state(self):
        return STATE_ON if self.is_on else STATE_OFF

    def update(self):
        try:
            self._state = self.virtualout.status
        except KeyError:
            _LOGGER.warning("Update of %s failed.", self._name)
            raise ConfigEntryNotReady


class DigitalInBinarySensor(IpxDevice, Entity):
    """Representation of a IPX Virtual In."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.digitalin = self.controller.ipx.digitalin[self.config.get("digitalin")]

    @property
    def device_class(self):
        return self._device_class

    @property
    def is_on(self):
        return bool(self._state)

    @property
    def state(self):
        return STATE_ON if self.is_on else STATE_OFF

    def update(self):
        try:
            self._state = self.digitalin.value
        except KeyError:
            _LOGGER.warning("Update of %s failed.", self._name)
            raise ConfigEntryNotReady
