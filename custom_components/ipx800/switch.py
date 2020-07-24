"""Support for IPX800 lights."""
import logging

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.components.switch import SwitchEntity

from pypx800 import *
from .device import *
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the IPX800 switches."""
    async_add_entities(
        [
            RelaySwitch(device)
            for device in (
                item
                for item in discovery_info
                if item.get("config").get(CONF_TYPE) == TYPE_RELAY
            )
        ],
        True,
    )


    # add_entities(
    #     [
    #         VirtualOutSwitch(device)
    #         for device in (
    #             item
    #             for item in hass.data[IPX800_DEVICES]["switch"]
    #             if item.get("config").get("virtualout")
    #         )
    #     ],
    #     True,
    # )

    # add_entities(
    #     [
    #         VirtualInSwitch(device)
    #         for device in (
    #             item
    #             for item in hass.data[IPX800_DEVICES]["switch"]
    #             if item.get("config").get("virtualin")
    #         )
    #     ],
    #     True,
    # )


class RelaySwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Switch through relay."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.control = Relay(self.controller.ipx, self._id)

    @property
    def is_on(self) -> bool:
        """Return true if the IPX800 device is on."""
        return self.coordinator.data[f"R{self._id}"] == 1

    def turn_on(self):
        """Turn on the IPX800 device."""
        self.control.on()

    def turn_off(self):
        """Turn off the IPX800 device."""
        self.control.off()


class VirtualOutSwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Virtual Out."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.virtualout = self.controller.ipx.virtualout[self.config.get("virtualout")]

    @property
    def is_on(self) -> bool:
        return self._state

    def turn_on(self):
        self.virtualout.on()
        self._state = True

    def turn_off(self):
        self.virtualout.off()
        self._state = False

    def toggle(self):
        self.virtualout.toggle()

    def update(self):
        try:
            self._state = self.virtualout.status
        except KeyError:
            _LOGGER.warning("Update of %s failed.", self._name)
            raise ConfigEntryNotReady


class VirtualInSwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Virtual In."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.virtualin = self.controller.ipx.virtualin[self.config.get("virtualin")]

    @property
    def is_on(self) -> bool:
        return self._state

    def turn_on(self):
        self.virtualin.on()
        self._state = True

    def turn_off(self):
        self.virtualin.off()
        self._state = False

    def toggle(self):
        self.virtualin.toggle()

    def update(self):
        try:
            self._state = self.virtualin.status
        except KeyError:
            _LOGGER.warning("Update of %s failed.", self._name)
            raise ConfigEntryNotReady
