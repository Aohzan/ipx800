"""Support for IPX800 V4 sensors."""

from dataclasses import dataclass
from datetime import datetime
import logging

from pypx800 import IPX800

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import LIGHT_LUX, Platform, UnitOfRatio, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_TYPE,
    GLOBAL_PARALLEL_UPDATES,
    TYPE_ANALOGIN,
    TYPE_COUNTER,
    TYPE_VIRTUALANALOGIN,
    TYPE_XENO,
    TYPE_XTHL,
)
from .coordinator import IpxConfigEntry, IpxDataUpdateCoordinator
from .entity import IpxDiagnosticEntity, IpxEntity

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IpxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the IPX800 sensors."""
    data = entry.runtime_data
    controller = data.controller
    coordinator = data.coordinator
    system_coordinator = data.system_coordinator
    devices = data.devices[Platform.SENSOR]

    entities: list[SensorEntity] = [
        IpxLastBootSensor(controller, system_coordinator, "last_boot"),
        IpxLoadSensor(controller, system_coordinator, "load"),
    ]

    # The diagnostics snapshot was loaded during setup. Adding these entities
    # must not request another XML read through update_before_add.
    async_add_entities(entities)
    entities = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_ANALOGIN:
            entities.append(AnalogInSensor(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_VIRTUALANALOGIN:
            entities.append(VirtualAnalogInSensor(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_COUNTER:
            entities.append(CounterSensor(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_XTHL:
            entities.extend(
                XTHLSensor(device, controller, coordinator, description)
                for description in XTHL_SENSORS
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

    _attr_state_class = SensorStateClass.MEASUREMENT
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


@dataclass(frozen=True, kw_only=True)
class XTHLSensorDescription:
    """Description of a X-THL measurement."""

    req_type: str
    # English name, part of the unique ID of the entities created before the
    # names were translated
    unique_suffix: str
    translation_key: str
    device_class: SensorDeviceClass
    unit: str


XTHL_SENSORS = (
    XTHLSensorDescription(
        req_type="TEMP",
        unique_suffix="Temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        unit=UnitOfTemperature.CELSIUS,
    ),
    XTHLSensorDescription(
        req_type="HUM",
        unique_suffix="Humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        unit=UnitOfRatio.PERCENTAGE,
    ),
    XTHLSensorDescription(
        req_type="LUM",
        unique_suffix="Luminance",
        translation_key="luminance",
        device_class=SensorDeviceClass.ILLUMINANCE,
        unit=LIGHT_LUX,
    ),
)


class XTHLSensor(IpxEntity, SensorEntity):
    """Representation of a X-THL sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: IpxDataUpdateCoordinator,
        description: XTHLSensorDescription,
    ) -> None:
        """Initialize the XTHLSensor."""
        super().__init__(device_config, ipx, coordinator, description.unique_suffix)
        self._attr_translation_key = description.translation_key
        self._attr_device_class = description.device_class
        self._attr_native_unit_of_measurement = description.unit
        self._req_type = description.req_type

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
