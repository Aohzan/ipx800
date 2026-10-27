"""Support for IPX800 V4 numbers."""

from pypx800 import IPX800, Counter, VAInput

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_TYPE,
    GLOBAL_PARALLEL_UPDATES,
    TYPE_COUNTER,
    TYPE_VIRTUALANALOGIN,
)
from .coordinator import IpxConfigEntry
from .entity import IpxEntity

PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IpxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the IPX800 numbers."""
    data = entry.runtime_data
    controller = data.controller
    coordinator = data.coordinator
    devices = data.devices[Platform.NUMBER]

    entities: list[NumberEntity] = []

    for device in devices:
        if device.get(CONF_TYPE) in [TYPE_VIRTUALANALOGIN, TYPE_COUNTER]:
            entities.append(VirtualAnalogInNumber(device, controller, coordinator))

    async_add_entities(entities, True)


class CounterNumber(IpxEntity, NumberEntity):
    """Representation of a IPX number through analog input."""

    _push_prefix = "C"

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
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"C{self._id}",)

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self.coordinator.data[f"C{self._id}"]

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        async with self._command_error("set value"):
            await self._async_write(self.control.set_value, value)


class VirtualAnalogInNumber(IpxEntity, NumberEntity):
    """Representation of a IPX number through virtual analog input."""

    _push_prefix = "VA"

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
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"VA{self._id}",)

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self.coordinator.data[f"VA{self._id}"]

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        async with self._command_error("set value"):
            await self._async_write(self.control.set_value, value, retry=True)
