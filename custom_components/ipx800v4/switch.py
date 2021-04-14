"""Support for IPX800 V4 switches."""
import logging

from pypx800 import IPX800, Ipx800RequestError, Relay, VInput, VOutput

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import IpxDevice
from .const import (
    CONF_DEVICES,
    CONF_TYPE,
    CONTROLLER,
    COORDINATOR,
    DOMAIN,
    GLOBAL_PARALLEL_UPDATES,
    TYPE_RELAY,
    TYPE_VIRTUALIN,
    TYPE_VIRTUALOUT,
)

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the IPX800 switches."""
    controller = hass.data[DOMAIN][entry.entry_id][CONTROLLER]
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    devices = hass.data[DOMAIN][entry.entry_id][CONF_DEVICES]["switch"]

    entities = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_RELAY:
            entities.append(RelaySwitch(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_VIRTUALOUT:
            entities.append(VirtualOutSwitch(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_VIRTUALIN:
            entities.append(VirtualInSwitch(device, controller, coordinator))

    async_add_entities(entities, True)


class RelaySwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Switch through relay."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ):
        """Initialize the RelaySwitch."""
        super().__init__(device_config, ipx, coordinator)
        self.control = Relay(ipx, self._id)

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.data[f"R{self._id}"] == 1

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the switch."""
        try:
            await self.control.on()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while toggle IPX800 switch: %s", self.name)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the switch."""
        try:
            await self.control.off()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turn off IPX800 switch: %s", self.name
            )

    async def async_toggle(self, **kwargs) -> None:
        """Toggle the switch."""
        try:
            await self.control.toggle()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while toggle IPX800 switch: %s", self.name)


class VirtualOutSwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Virtual Out."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ):
        """Initialize the VirtualOutSwitch."""
        super().__init__(device_config, ipx, coordinator)
        self.control = VOutput(ipx, self._id)

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.data[f"VO{self._id}"] == 1

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the switch."""
        try:
            await self.control.on()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turn on IPX800 switch: %s", self.name
            )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the switch."""
        try:
            await self.control.off()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turn off IPX800 switch: %s", self.name
            )

    async def async_toggle(self, **kwargs) -> None:
        """Toggle the switch."""
        try:
            await self.control.toggle()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while toggle IPX800 switch: %s", self.name)


class VirtualInSwitch(IpxDevice, SwitchEntity):
    """Representation of a IPX Virtual In."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ):
        """Initialize the VirtualInSwitch."""
        super().__init__(device_config, ipx, coordinator)
        self.control = VInput(ipx, self._id)

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.data[f"VI{self._id}"] == 1

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the switch."""
        try:
            await self.control.on()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turn on IPX800 switch: %s", self.name
            )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the switch."""
        try:
            await self.control.off()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turn off IPX800 switch: %s", self.name
            )

    async def async_toggle(self, **kwargs) -> None:
        """Toggle the switch."""
        try:
            await self.control.toggle()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while toggle IPX800 switch: %s", self.name)
