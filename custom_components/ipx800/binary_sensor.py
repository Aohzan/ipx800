"""Support for IPX800 binary sensors."""
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.entity import Entity
from pypx800 import *

from . import IpxController, IpxDevice
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Set up the IPX800 binary sensors."""
    controller = hass.data[DOMAIN][config_entry.entry_id][CONTROLLER]
    devices = [
        d
        for d in config_entry.data.get(CONF_DEVICES)
        if d.get(CONF_COMPONENT) == "binary_sensor"
    ]

    async_add_entities(
        [
            VirtualOutBinarySensor(device, controller)
            for device in (d for d in devices if d.get(CONF_TYPE) == TYPE_VIRTUALOUT)
        ],
        True,
    )

    async_add_entities(
        [
            DigitalInBinarySensor(device, controller)
            for device in (d for d in devices if d.get(CONF_TYPE) == TYPE_DIGITALIN)
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
