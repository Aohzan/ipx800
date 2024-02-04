"""Support for IPX800 V4 binary sensors."""
import logging

from pypx800 import IPX800

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import IpxEntity
from .const import (
    CONF_DEVICES,
    CONF_INVERT,
    CONF_TYPE,
    CONTROLLER,
    COORDINATOR,
    DOMAIN,
    GLOBAL_PARALLEL_UPDATES,
    TYPE_DIGITALIN,
    TYPE_VIRTUALOUT,
)

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IPX800 binary sensors."""
    controller = hass.data[DOMAIN][entry.entry_id][CONTROLLER]
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    devices = hass.data[DOMAIN][entry.entry_id][CONF_DEVICES]["binary_sensor"]

    entities: list[BinarySensorEntity] = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_VIRTUALOUT:
            on_value = 0 if device.get(CONF_INVERT) else 1
            entities.append(VirtualOutBinarySensor(device, controller, coordinator, on_value))
        elif device.get(CONF_TYPE) == TYPE_DIGITALIN:
            on_value = 0 if device.get(CONF_INVERT) else 1
            entities.append(DigitalInBinarySensor(device, controller, coordinator, on_value))

    async_add_entities(entities, True)


class VirtualOutBinarySensor(IpxEntity, BinarySensorEntity):
    """Representation of a IPX Virtual Out."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
        on_value: int
    ) -> None:
        """Initialize the VirtualOutBinarySensor."""
        super().__init__(device_config, ipx, coordinator)
        self.on_value = on_value

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.data[f"VO{self._id}"] == self.on_value


class DigitalInBinarySensor(IpxEntity, BinarySensorEntity):
    """Representation of a IPX Virtual In."""

     def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
        on_value: int
    ) -> None:
        """Initialize the DigitalInBinarySensor."""
        super().__init__(device_config, ipx, coordinator)
        self.on_value = on_value

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.data[f"D{self._id}"] == self.on_value
