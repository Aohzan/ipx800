"""Support for IPX800 sensors."""
import logging

from homeassistant.const import (
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_ILLUMINANCE,
    DEVICE_CLASS_TEMPERATURE,
)
from homeassistant.helpers.entity import Entity
from pypx800 import *

from . import IpxController, IpxDevice
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Set up the IPX800 sensors."""
    controller = hass.data[DOMAIN][config_entry.entry_id][CONTROLLER]
    devices = [
        d
        for d in config_entry.data.get(CONF_DEVICES)
        if d.get(CONF_COMPONENT) == "sensor"
    ]

    async_add_entities(
        [
            AnalogInSensor(device, controller)
            for device in (d for d in devices if d.get(CONF_TYPE) == TYPE_ANALOGIN)
        ],
        True,
    )

    for device in (d for d in devices if d.get(CONF_TYPE) == TYPE_XTHL):
        async_add_entities(
            [
                XTHLSensor(
                    device,
                    controller,
                    DEVICE_CLASS_TEMPERATURE,
                    "°C",
                    "TEMP",
                    "Temperature",
                ),
                XTHLSensor(
                    device, controller, DEVICE_CLASS_HUMIDITY, "%", "HUM", "Humidity"
                ),
                XTHLSensor(
                    device,
                    controller,
                    DEVICE_CLASS_ILLUMINANCE,
                    "lx",
                    "LUM",
                    "Luminance",
                ),
            ],
            True,
        )


class AnalogInSensor(IpxDevice, Entity):
    """Representation of a IPX sensor through analog input."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)

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
        self,
        device_config,
        controller: IpxController,
        device_class,
        unit_of_measurement,
        req_type,
        suffix_name,
    ):
        super().__init__(device_config, controller, suffix_name)
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
        return round(self.coordinator.data[f"THL{self._id}-{self._req_type}"], 1)
