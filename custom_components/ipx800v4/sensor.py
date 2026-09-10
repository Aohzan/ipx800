"""Support for IPX800 V4 sensors."""

from datetime import datetime
import logging

from pypx800 import IPX800

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
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
    TYPE_ANALOGIN,
    TYPE_COUNTER,
    TYPE_VIRTUALANALOGIN,
    TYPE_XENO,
    TYPE_XTHL,
)
from .entity import IpxDiagnosticEntity, IpxEntity

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IPX800 sensors."""
    controller = hass.data[DOMAIN][entry.entry_id][CONTROLLER]
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    devices = hass.data[DOMAIN][entry.entry_id][CONF_DEVICES]["sensor"]

    entities: list[SensorEntity] = [
        IpxLastBootSensor(controller, coordinator, "last_boot"),
        IpxLoadSensor(controller, coordinator, "load"),
    ]

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_ANALOGIN:
            entities.append(AnalogInSensor(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_VIRTUALANALOGIN:
            entities.append(VirtualAnalogInSensor(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_COUNTER:
            entities.append(CounterSensor(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_XTHL:
            entities.append(
                XTHLSensor(
                    device,
                    controller,
                    coordinator,
                    SensorDeviceClass.TEMPERATURE,
                    "°C",
                    "TEMP",
                    suffix_name="Temperature",
                )
            )
            entities.append(
                XTHLSensor(
                    device,
                    controller,
                    coordinator,
                    SensorDeviceClass.HUMIDITY,
                    "%",
                    "HUM",
                    suffix_name="Humidity",
                )
            )
            entities.append(
                XTHLSensor(
                    device,
                    controller,
                    coordinator,
                    SensorDeviceClass.ILLUMINANCE,
                    "lx",
                    "LUM",
                    suffix_name="Luminance",
                )
            )
        elif device.get(CONF_TYPE) == TYPE_XENO:
            entities.append(
                XENOSensor(
                    device,
                    controller,
                    coordinator,
                )
            )

    async_add_entities(entities, True)


class AnalogInSensor(IpxEntity, SensorEntity):
    """Representation of a IPX sensor through analog input."""

    _push_prefix = "A"

    @property
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"A{self._id}",)

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self.coordinator.data[f"A{self._id}"]


class CounterSensor(IpxEntity, SensorEntity):
    """Representation of a IPX sensor through analog input."""

    _push_prefix = "C"

    @property
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"C{self._id}",)

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self.coordinator.data[f"C{self._id}"]


class VirtualAnalogInSensor(IpxEntity, SensorEntity):
    """Representation of a IPX sensor through virtual analog input."""

    _push_prefix = "VA"

    @property
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"VA{self._id}",)

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self.coordinator.data[f"VA{self._id}"]


class XTHLSensor(IpxEntity, SensorEntity):
    """Representation of a X-THL sensor."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
        device_class: SensorDeviceClass,
        unit_of_measurement: str,
        req_type: str,
        suffix_name: str,
    ) -> None:
        """Initialize the XTHLSensor."""
        super().__init__(device_config, ipx, coordinator, suffix_name)
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._req_type = req_type

    @property
    def push_key(self) -> str:
        """Return the raw measurement field."""
        return f"THL{self._id}-{self._req_type}"

    @property
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"THL{self._id}-{self._req_type}",)

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return round(self.coordinator.data[f"THL{self._id}-{self._req_type}"], 1)


class XENOSensor(IpxEntity, SensorEntity):
    """Representation of an Enocean sensor."""

    @property
    def push_key(self) -> str:
        """Return the raw measurement field."""
        return f"ENO ANALOG{int(self._id) - 121 + 17}"

    @property
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        analog_id = int(self._id) - 121 + 17
        return (f"ENO ANALOG{analog_id}",)

    @property
    def native_value(self) -> float:
        """Return the current value."""
        analog_id = int(self._id) - 121 + 17
        return round(self.coordinator.data[f"ENO ANALOG{analog_id}"], 1)


class IpxLastBootSensor(IpxDiagnosticEntity, SensorEntity):
    """Controller boot time calculated from its uptime."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Return a stable, timezone-aware last boot timestamp."""
        return self.system_data.get(self._key)


class IpxLoadSensor(IpxDiagnosticEntity, SensorEntity):
    """Controller processing capacity in loops per second."""

    _attr_native_unit_of_measurement = "loops/s"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the raw load indicator; lower values mean higher load."""
        return self.system_data.get(self._key)
