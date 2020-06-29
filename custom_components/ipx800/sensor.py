"""Support for IPX800 sensors."""
import logging

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.components.sensor import DOMAIN
from homeassistant.helpers.entity import Entity

from . import IPX800_DEVICES, IpxDevice

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the IPX800 sensors."""

    add_entities(
        [
            AnalogInSensor(device)
            for device in (
                item
                for item in hass.data[IPX800_DEVICES]["sensor"]
                if item.get("config").get("analogin")
            )
        ],
        True,
    )


class AnalogInSensor(IpxDevice, Entity):
    """Representation of a IPX sensor through analog input."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.analogin = self.controller.ipx.analogin[self.config.get("analogin")]

    @property
    def device_class(self):
        return self._device_class

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @property
    def state(self) -> float:
        return self._state

    def update(self):
        try:
            self._state = float(self.analogin.value)
        except:
            _LOGGER.warning("Update of %s failed.", self._name)
            raise ConfigEntryNotReady
