"""Support for IPX800 V4 numbers."""

import logging

from pypx800 import IPX800, Counter, VAInput

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_DEVICES,
    CONF_TYPE,
    CONTROLLER,
    COORDINATOR,
    DOMAIN,
    GLOBAL_PARALLEL_UPDATES,
    TYPE_COUNTER,
    TYPE_VIRTUALANALOGIN,
)
from .entity import IpxEntity

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IPX800 numbers."""
    controller = hass.data[DOMAIN][entry.entry_id][CONTROLLER]
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    devices = hass.data[DOMAIN][entry.entry_id][CONF_DEVICES]["number"]

    entities: list[NumberEntity] = []

    for device in devices:
        if device.get(CONF_TYPE) in [TYPE_VIRTUALANALOGIN, TYPE_COUNTER]:
            entities.append(VirtualAnalogInNumber(device, controller, coordinator))  # noqa: PERF401

    async_add_entities(entities, True)


class CounterNumber(IpxEntity, NumberEntity):
    """Representation of a IPX number through analog input."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 21474836

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the RelayLight."""
        super().__init__(device_config, ipx, coordinator)
        self.control = Counter(ipx, self._id)

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self.coordinator.data[f"C{self._id}"]

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self.control.set_value(value)


class VirtualAnalogInNumber(IpxEntity, NumberEntity):
    """Representation of a IPX number through virtual analog input."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the RelayLight."""
        super().__init__(device_config, ipx, coordinator)
        self.control = VAInput(ipx, self._id)

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self.coordinator.data[f"VA{self._id}"]

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self.control.set_value(value)
