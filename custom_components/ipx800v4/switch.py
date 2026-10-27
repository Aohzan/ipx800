"""Support for IPX800 V4 switches."""

from typing import Any

from pypx800 import IPX800, Relay, VInput, VOutput

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_TYPE,
    GLOBAL_PARALLEL_UPDATES,
    TYPE_RELAY,
    TYPE_VIRTUALIN,
    TYPE_VIRTUALOUT,
    TYPE_XENO,
)
from .coordinator import IpxConfigEntry
from .entity import IpxEntity

PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IpxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the IPX800 switches."""
    data = entry.runtime_data
    controller = data.controller
    coordinator = data.coordinator
    devices = data.devices[Platform.SWITCH]

    entities: list[SwitchEntity] = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_RELAY:
            entities.append(RelaySwitch(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_VIRTUALOUT:
            entities.append(VirtualOutSwitch(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_VIRTUALIN:
            entities.append(VirtualInSwitch(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_XENO:
            entities.append(XENOSwitch(device, controller, coordinator))

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
        async with self._command_error("turn_on", target=("state", 1)):
            await self._async_write(self.control.on, retry=True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        async with self._command_error("turn_off", target=("state", 0)):
            await self._async_write(self.control.off, retry=True)
        await self.coordinator.async_request_refresh()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the switch."""
        async with self._command_error("toggle"):
            await self._async_write(self.control.toggle)
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
        async with self._command_error("turn_on", target=("state", 1)):
            await self._async_write(self.control.on, retry=True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        async with self._command_error("turn_off", target=("state", 0)):
            await self._async_write(self.control.off, retry=True)
        await self.coordinator.async_request_refresh()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the switch."""
        async with self._command_error("toggle"):
            await self._async_write(self.control.toggle)
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
        async with self._command_error("turn_on", target=("state", 1)):
            await self._async_write(self.control.on, retry=True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        async with self._command_error("turn_off", target=("state", 0)):
            await self._async_write(self.control.off, retry=True)
        await self.coordinator.async_request_refresh()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the switch."""
        async with self._command_error("toggle"):
            await self._async_write(self.control.toggle)
        await self.coordinator.async_request_refresh()


class XENOActuator:
    """EnOcean actuator commands, not provided by pypx800."""

    def __init__(self, ipx800: IPX800, actuator_id: int) -> None:
        """Initialize object."""
        self._ipx = ipx800
        self.id = actuator_id

    async def on(self) -> None:
        """Turn on an EnOcean actuator."""
        await self._ipx.request_api({"SetEnoPC": self.id})

    async def off(self) -> None:
        """Turn off an EnOcean actuator."""
        await self._ipx.request_api({"ClearEnoPC": self.id})

    async def toggle(self) -> None:
        """Toggle an EnOcean actuator."""
        await self._ipx.request_api({"ToggleEnoPC": self.id})


class XENOSwitch(IpxEntity, SwitchEntity):
    """Representation of an EnOcean actuator."""

    _push_prefix = "ENO ACTIONNEUR"
    _push_binary = True

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the XENOSwitch."""
        super().__init__(device_config, ipx, coordinator)
        self.control = XENOActuator(ipx, self._id)

    @property
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"ENO ACTIONNEUR{self._id}",)

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.data[f"ENO ACTIONNEUR{self._id}"] == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        async with self._command_error("turn_on", target=("state", 1)):
            await self._async_write(self.control.on, retry=True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        async with self._command_error("turn_off", target=("state", 0)):
            await self._async_write(self.control.off, retry=True)
        await self.coordinator.async_request_refresh()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the switch."""
        async with self._command_error("toggle"):
            await self._async_write(self.control.toggle)
        await self.coordinator.async_request_refresh()
