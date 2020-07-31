"""Support for IPX800 sensors."""
import logging

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity import Entity
from homeassistant.const import (
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_ILLUMINANCE,
    DEVICE_CLASS_TEMPERATURE,
)

from pypx800 import *
from .device import *
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the IPX800 sensors."""

    async_add_entities(
        [
            AnalogInSensor(device)
            for device in (
                item
                for item in discovery_info
                if item.get("config").get(CONF_TYPE) == TYPE_ANALOGIN
            )
        ],
        True,
    )

    """ X-THL sensors """
    for device in (
        item
        for item in discovery_info
        if item.get("config").get(CONF_TYPE) == TYPE_XTHL
    ):
        async_add_entities(
            [
                XTHLSensor(
                    device, DEVICE_CLASS_TEMPERATURE, "°C", "TEMP", "Temperature"
                ),
                XTHLSensor(device, DEVICE_CLASS_HUMIDITY, "%", "HUM", "Humidity"),
                XTHLSensor(device, DEVICE_CLASS_ILLUMINANCE, "lx", "LUM", "Luminance"),
            ],
            True,
        )


class AnalogInSensor(IpxDevice, Entity):
    """Representation of a IPX sensor through analog input."""

    def __init__(self, ipx_device):
        super().__init__(ipx_device)

    @property
    def device_class(self):
        return self._device_class

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @property
    def state(self) -> str:
        return self.coordinator.data[f"A{self._id}"]


class XTHLSensor(IpxDevice, Entity):
    """Representation of a X-THL sensor."""

    def __init__(
        self, ipx_device, device_class, unit_of_measurement, req_type, name_suffix
    ):
        super().__init__(ipx_device, name_suffix)
        self._device_class = device_class
        """Allow overriding of temperature unit if specified in the xthl conf"""
        if not (self._unit_of_measurement and device_class == DEVICE_CLASS_TEMPERATURE):
            self._unit_of_measurement = unit_of_measurement
        self._req_type = req_type

    @property
    def device_class(self):
        return self._device_class

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @property
    def state(self) -> str:
        return self.coordinator.data[f"THL{self._id}-{self._req_type}"]
