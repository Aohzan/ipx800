"""Support for IPX800 switches."""
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

    async_add_entities(
        [
            VirtualOutSwitch(device)
            for device in (
                item
                for item in discovery_info
                if item.get("config").get(CONF_TYPE) == TYPE_VIRTUALOUT
            )
        ],
        True,
    )

    async_add_entities(
        [
            VirtualInSwitch(device)
            for device in (
                item
                for item in discovery_info
                if item.get("config").get(CONF_TYPE) == TYPE_VIRTUALIN
            )
        ],
        True,
    )


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

    def turn_on(self, **kwargs):
        """Turn on the IPX800 device."""
        self.control.on()

    def turn_off(self, **kwargs):
        """Turn off the IPX800 device."""
        self.control.off()


class VirtualOutSwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Virtual Out."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.control = VOutput(self.controller.ipx, self._id)

    @property
    def is_on(self) -> bool:
        """Return true if the IPX800 device is on."""
        return self.coordinator.data[f"R{self._id}"] == 1

    def turn_on(self, **kwargs):
        """Turn on the IPX800 device."""
        self.control.on()

    def turn_off(self, **kwargs):
        """Turn off the IPX800 device."""
        self.control.off()

    def toggle(self, **kwargs):
        """Toggle the IPX800 device."""
        self.control.toggle()


class VirtualInSwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Virtual In."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.control = VInput(self.controller.ipx, self._id)

    @property
    def is_on(self) -> bool:
        """Return true if the IPX800 device is on."""
        return self.coordinator.data[f"VI{self._id}"] == 1

    def turn_on(self, **kwargs):
        """Turn on the IPX800 device."""
        self.control.on()

    def turn_off(self, **kwargs):
        """Turn off the IPX800 device."""
        self.control.off()

    def toggle(self, **kwargs):
        """Toggle the IPX800 device."""
        self.control.toggle()
