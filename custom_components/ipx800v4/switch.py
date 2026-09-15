"""Support for IPX800 V4 switches."""

from typing import Any

from pypx800 import IPX800, Relay, VInput, VOutput

from homeassistant.components.switch import SwitchEntity
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
    TYPE_RELAY,
    TYPE_VIRTUALIN,
    TYPE_VIRTUALOUT,
)
from .entity import IpxEntity

PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IPX800 switches."""
    controller = hass.data[DOMAIN][entry.entry_id][CONTROLLER]
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    devices = hass.data[DOMAIN][entry.entry_id][CONF_DEVICES]["switch"]

    entities: list[SwitchEntity] = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_RELAY:
            entities.append(RelaySwitch(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_VIRTUALOUT:
            entities.append(VirtualOutSwitch(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_VIRTUALIN:
            entities.append(VirtualInSwitch(device, controller, coordinator))

    async_add_entities(entities, True)


class RelaySwitch(IpxEntity, SwitchEntity):
    """Representation of a IPX Switch through relay."""

    _push_prefix = "R"
    _push_binary = True

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the RelaySwitch."""
        super().__init__(device_config, ipx, coordinator)
        self.control = Relay(ipx, self._id)

    @property
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"R{self._id}",)

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.data[f"R{self._id}"] == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        with self._command_error("turn on"):
            await self.control.on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        with self._command_error("turn off"):
            await self.control.off()
        await self.coordinator.async_request_refresh()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the switch."""
        with self._command_error("toggle"):
            await self.control.toggle()
        await self.coordinator.async_request_refresh()


class VirtualOutSwitch(IpxEntity, SwitchEntity):
    """Representation of a IPX Virtual Out."""

    _push_prefix = "VO"
    _push_binary = True

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the VirtualOutSwitch."""
        super().__init__(device_config, ipx, coordinator)
        self.control = VOutput(ipx, self._id)

    @property
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"VO{self._id}",)

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.data[f"VO{self._id}"] == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        with self._command_error("turn on"):
            await self.control.on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        with self._command_error("turn off"):
            await self.control.off()
        await self.coordinator.async_request_refresh()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the switch."""
        with self._command_error("toggle"):
            await self.control.toggle()
        await self.coordinator.async_request_refresh()


class VirtualInSwitch(IpxEntity, SwitchEntity):
    """Representation of a IPX Virtual In."""

    _push_prefix = "VI"
    _push_binary = True

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the VirtualInSwitch."""
        super().__init__(device_config, ipx, coordinator)
        self.control = VInput(ipx, self._id)

    @property
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"VI{self._id}",)

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.data[f"VI{self._id}"] == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        with self._command_error("turn on"):
            await self.control.on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        with self._command_error("turn off"):
            await self.control.off()
        await self.coordinator.async_request_refresh()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the switch."""
        with self._command_error("toggle"):
            await self.control.toggle()
        await self.coordinator.async_request_refresh()
