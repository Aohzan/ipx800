"""Support for IPX800 V4 sensors."""
import logging

from pypx800 import IPX800

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_ILLUMINANCE,
    DEVICE_CLASS_TEMPERATURE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import IpxDevice
from .const import (
    CONF_DEVICES,
    CONF_TYPE,
    CONTROLLER,
    COORDINATOR,
    DOMAIN,
    GLOBAL_PARALLEL_UPDATES,
    TYPE_ANALOGIN,
    TYPE_XTHL,
)

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the IPX800 sensors."""
    controller = hass.data[DOMAIN][entry.entry_id][CONTROLLER]
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    devices = hass.data[DOMAIN][entry.entry_id][CONF_DEVICES]["sensor"]

    entities = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_ANALOGIN:
            entities.append(AnalogInSensor(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_XTHL:
            entities.append(
                XTHLSensor(
                    device,
                    controller,
                    coordinator,
                    DEVICE_CLASS_TEMPERATURE,
                    "°C",
                    "TEMP",
                    "Temperature",
                )
            )
            entities.append(
                XTHLSensor(
                    device,
                    controller,
                    coordinator,
                    DEVICE_CLASS_HUMIDITY,
                    "%",
                    "HUM",
                    "Humidity",
                )
            )
            entities.append(
                XTHLSensor(
                    device,
                    controller,
                    coordinator,
                    DEVICE_CLASS_ILLUMINANCE,
                    "lx",
                    "LUM",
                    "Luminance",
                )
            )

    async_add_entities(entities, True)


class AnalogInSensor(IpxDevice, Entity):
    """Representation of a IPX sensor through analog input."""

    @property
    def device_class(self):
        """Return the device class."""
        return self._device_class

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def state(self) -> str:
        """Return the state."""
        return self.coordinator.data[f"A{self._id}"]


class XTHLSensor(IpxDevice, Entity):
    """Representation of a X-THL sensor."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
        device_class: str,
        unit_of_measurement: str,
        req_type: str,
        suffix_name: str,
    ):
        """Initialize the XTHLSensor."""
        super().__init__(device_config, ipx, coordinator, suffix_name)
        self._device_class = device_class
        # Allow overriding of temperature unit if specified in the xthl conf
        if not (self._unit_of_measurement and device_class == DEVICE_CLASS_TEMPERATURE):
            self._unit_of_measurement = unit_of_measurement
        self._req_type = req_type

    @property
    def device_class(self):
        """Return the device class."""
        return self._device_class

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def state(self) -> str:
        """Return the state."""
        return round(self.coordinator.data[f"THL{self._id}-{self._req_type}"], 1)
