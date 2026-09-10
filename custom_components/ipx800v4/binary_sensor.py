"""Support for IPX800 V4 binary sensors."""

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEVICES,
    CONF_TYPE,
    CONTROLLER,
    COORDINATOR,
    DOMAIN,
    GLOBAL_PARALLEL_UPDATES,
    TYPE_DIGITALIN,
    TYPE_VIRTUALOUT,
)
from .entity import IpxDiagnosticEntity, IpxEntity

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

    entities: list[BinarySensorEntity] = [
        IpxClockBinarySensor(controller, coordinator, "clock_in_sync")
    ]

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_VIRTUALOUT:
            entities.append(VirtualOutBinarySensor(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_DIGITALIN:
            entities.append(DigitalInBinarySensor(device, controller, coordinator))

    async_add_entities(entities, True)


class VirtualOutBinarySensor(IpxEntity, BinarySensorEntity):
    """Representation of a IPX Virtual Out."""

    _push_prefix = "VO"
    _push_binary = True
    _push_invert = True

    @property
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"VO{self._id}",)

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.data[f"VO{self._id}"] == (
            1 if not self._invert_value else 0
        )


class DigitalInBinarySensor(IpxEntity, BinarySensorEntity):
    """Representation of a IPX Virtual In."""

    _push_prefix = "D"
    _push_binary = True
    _push_invert = True

    @property
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"D{self._id}",)

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.data[f"D{self._id}"] == (
            1 if not self._invert_value else 0
        )


class IpxClockBinarySensor(IpxDiagnosticEntity, BinarySensorEntity):
    """Whether the controller clock agrees with Home Assistant's local time."""

    @property
    def is_on(self) -> bool | None:
        """Return True when the clock differs by no more than 60 seconds."""
        return self.system_data.get(self._key)

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the signed clock offset in seconds (IPX minus HA)."""
        return {"clock_offset_seconds": self.system_data.get("clock_offset")}
