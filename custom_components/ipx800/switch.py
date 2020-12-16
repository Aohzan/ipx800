"""Support for IPX800 switches."""
import logging

from homeassistant.components.switch import SwitchEntity
from pypx800 import *

from . import IpxController, IpxDevice
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Set up the IPX800 switches."""
    controller = hass.data[DOMAIN][config_entry.entry_id][CONTROLLER]
    devices = filter(
        lambda d: d[CONF_COMPONENT] == "switch", config_entry.data[CONF_DEVICES]
    )

    entities = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_RELAY:
            entities.append(RelaySwitch(device, controller))
        elif device.get(CONF_TYPE) == TYPE_VIRTUALOUT:
            entities.append(VirtualOutSwitch(device, controller))
        elif device.get(CONF_TYPE) == TYPE_VIRTUALIN:
            entities.append(VirtualInSwitch(device, controller))

    async_add_entities(entities, True)


class RelaySwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Switch through relay."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.control = Relay(controller.ipx, self._id)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data[f"R{self._id}"] == 1

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_job(self.control.on)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_job(self.control.off)
        await self.coordinator.async_request_refresh()

    async def async_toggle(self, **kwargs):
        await self.hass.async_add_job(self.control.toggle)
        await self.coordinator.async_request_refresh()


class VirtualOutSwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Virtual Out."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.control = VOutput(controller.ipx, self._id)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data[f"R{self._id}"] == 1

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_job(self.control.on)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_job(self.control.off)
        await self.coordinator.async_request_refresh()

    async def async_toggle(self, **kwargs):
        await self.hass.async_add_job(self.control.toggle)
        await self.coordinator.async_request_refresh()


class VirtualInSwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Virtual In."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.control = VInput(controller.ipx, self._id)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data[f"VI{self._id}"] == 1

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_job(self.control.on)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_job(self.control.off)
        await self.coordinator.async_request_refresh()

    async def async_toggle(self, **kwargs):
        await self.hass.async_add_job(self.control.toggle)
        await self.coordinator.async_request_refresh()
