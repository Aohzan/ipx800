"""Support for IPX800 lights."""
import logging

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.components.switch import (
    DOMAIN,
    SwitchEntity,
)

from . import IPX800_DEVICES, IpxDevice

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the IPX800 switches."""

    add_entities(
        [
            RelaySwitch(device)
            for device in (
                item
                for item in hass.data[IPX800_DEVICES]["switch"]
                if item.get("config").get("relay")
            )
        ],
        True,
    )

    add_entities(
        [
            VirtualOutSwitch(device)
            for device in (
                item
                for item in hass.data[IPX800_DEVICES]["switch"]
                if item.get("config").get("virtualout")
            )
        ],
        True,
    )

    add_entities(
        [
            VirtualInSwitch(device)
            for device in (
                item
                for item in hass.data[IPX800_DEVICES]["switch"]
                if item.get("config").get("virtualin")
            )
        ],
        True,
    )


class RelaySwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Switch through relay."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.relay = self.controller.ipx.relays[self.config.get("relay")]

    @property
    def is_on(self) -> bool:
        return self._state

    def turn_on(self):
        """Turn on the IPX800 device."""
        self.relay.on()
        self._state = True

    def turn_off(self):
        """Turn off the IPX800 device."""
        self.relay.off()
        self._state = False

    def toggle(self):
        """Toggle the IPX800 device."""
        self.relay.toggle()

    def update(self):
        """Update the IPX800 device status."""
        try:
            self._state = self.relay.status
        except:
            _LOGGER.warning("Update of %s failed.", self._name)
            raise ConfigEntryNotReady


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
        except:
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
        except:
            _LOGGER.warning("Update of %s failed.", self._name)
            raise ConfigEntryNotReady
