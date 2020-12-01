"""Support for IPX800 switches."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import ConfigEntryNotReady
from pypx800 import *

from . import IpxController, IpxDevice
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the IPX800 switches."""
    controller = hass.data[DOMAIN][discovery_info[CONTROLLER]]

    async_add_entities(
        [
            RelaySwitch(device, controller)
            for device in (
                item
                for item in discovery_info[CONF_DEVICES]
                if item.get(CONF_TYPE) == TYPE_RELAY
            )
        ],
        True,
    )

    async_add_entities(
        [
            VirtualOutSwitch(device, controller)
            for device in (
                item
                for item in discovery_info[CONF_DEVICES]
                if item.get(CONF_TYPE) == TYPE_VIRTUALOUT
            )
        ],
        True,
    )

    async_add_entities(
        [
            VirtualInSwitch(device, controller)
            for device in (
                item
                for item in discovery_info[CONF_DEVICES]
                if item.get(CONF_TYPE) == TYPE_VIRTUALIN
            )
        ],
        True,
    )


class RelaySwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Switch through relay."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.control = Relay(controller.ipx, self._id)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data[f"R{self._id}"] == 1

    def turn_on(self, **kwargs):
        self.control.on()

    def turn_off(self, **kwargs):
        self.control.off()


class VirtualOutSwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Virtual Out."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.control = VOutput(controller.ipx, self._id)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data[f"R{self._id}"] == 1

    def turn_on(self, **kwargs):
        self.control.on()

    def turn_off(self, **kwargs):
        self.control.off()

    def toggle(self, **kwargs):
        self.control.toggle()


class VirtualInSwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Virtual In."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.control = VInput(controller.ipx, self._id)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data[f"VI{self._id}"] == 1

    def turn_on(self, **kwargs):
        self.control.on()

    def turn_off(self, **kwargs):
        self.control.off()

    def toggle(self, **kwargs):
        self.control.toggle()
