"""Support for IPX800 binary sensors."""
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity import Entity
from pypx800 import *

from . import IpxController, IpxDevice
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the IPX800 binary_sensors."""
    controller = hass.data[DOMAIN][discovery_info[CONTROLLER]]

    async_add_entities(
        [
            VirtualOutBinarySensor(device, controller)
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
            DigitalInBinarySensor(device, controller)
            for device in (
                item
                for item in discovery_info[CONF_DEVICES]
                if item.get(CONF_TYPE) == TYPE_DIGITALIN
            )
        ],
        True,
    )


class VirtualOutBinarySensor(IpxDevice, BinarySensorEntity):
    """Representation of a IPX Virtual Out."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)

    @property
    def device_class(self):
        return self._device_class

    @property
    def is_on(self) -> bool:
        return self.coordinator.data[f"VO{self._id}"] == 1


class DigitalInBinarySensor(IpxDevice, BinarySensorEntity):
    """Representation of a IPX Virtual In."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)

    @property
    def device_class(self):
        return self._device_class

    @property
    def is_on(self) -> bool:
        return self.coordinator.data[f"D{self._id}"] == 1
