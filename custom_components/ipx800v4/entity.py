"""Generic IPX800V4 entity."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from math import isfinite

from pypx800 import IPX800

from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_ICON,
    CONF_NAME,
    CONF_UNIT_OF_MEASUREMENT,
    EntityCategory,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import slugify

from .const import (
    CONF_COMPONENT,
    CONF_EXT_ID,
    CONF_ID,
    CONF_IDS,
    CONF_INVERT_VALUE,
    CONF_TRANSITION,
    CONF_RETRY_COMMANDS,
    CONF_TYPE,
    DEFAULT_TRANSITION,
    DOMAIN,
    TYPE_ANALOGIN,
    TYPE_DIGITALIN,
    TYPE_RELAY,
    TYPE_VIRTUALANALOGIN,
    TYPE_VIRTUALIN,
    TYPE_VIRTUALOUT,
    TYPE_X4VR,
    TYPE_X4VR_BSO,
    TYPE_XDIMMER,
    TYPE_XPWM,
    TYPE_XPWM_RGB,
    TYPE_XPWM_RGBW,
    TYPE_XTHL,
)
from .coordinator import IpxDataUpdateCoordinator
from .commands import CommandFailure


class IpxEntity(CoordinatorEntity):
    """Representation of a IPX800 generic device entity."""

    _push_prefix: str | None = None
    _push_binary = False
    _push_invert = False

    @asynccontextmanager
    async def _command_error(self, operation: str) -> AsyncIterator[None]:
        """Report expected write failures; keep refreshes outside this boundary."""
        try:
            async with self.coordinator.commands.operation(self.required_keys):
                yield
        except CommandFailure as err:
            raise HomeAssistantError(
                f"Cannot confirm {operation} for {self.entity_id or self.name}: "
                f"{err}. Check device state before issuing another command."
            ) from err.error

    async def _async_write(self, command, *args, retry: bool = False, **kwargs) -> None:
        """Execute one write with an explicit replay policy and fixed arguments."""
        await self.coordinator.commands.write(
            self.required_keys,
            command,
            *args,
            retry=retry and self._retry_commands,
            **kwargs,
        )

    async def async_added_to_hass(self) -> None:
        """Register the live entity by its stable registry identity."""
        self.coordinator.register_fields(self.required_keys)
        self.async_on_remove(
            lambda: self.coordinator.unregister_fields(self.required_keys)
        )
        await super().async_added_to_hass()
        self.coordinator.push_entities[self.unique_id] = self
        self.async_on_remove(self._remove_push_entity)

    def _remove_push_entity(self) -> None:
        """Do not remove a replacement entity during late cleanup."""
        if self.coordinator.push_entities.get(self.unique_id) is self:
            self.coordinator.push_entities.pop(self.unique_id)

    @property
    def push_key(self) -> str | None:
        """Raw scalar field represented by this entity, if unambiguous."""
        return f"{self._push_prefix}{self._id}" if self._push_prefix else None

    def push_values(self, state: str) -> dict:
        """Convert an entity state to raw data without issuing a command."""
        key = self.push_key
        if key is None:
            raise ValueError("This entity requires a full refresh push")
        if self._push_binary:
            states = {"on": 1, "true": 1, "1": 1, "off": 0, "false": 0, "0": 0}
            if state.lower() not in states:
                raise ValueError("Expected on/off, true/false or 1/0")
            value = states[state.lower()]
            if self._push_invert and self._invert_value:
                value = 1 - value
        else:
            try:
                value = float(state)
            except ValueError:
                raise ValueError("Expected a numeric field value") from None
            if not isfinite(value):
                raise ValueError("Expected a finite field value")
        return {key: value}

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: IpxDataUpdateCoordinator,
        suffix_name: str = "",
    ) -> None:
        """Initialize the device."""
        super().__init__(coordinator)

        self._retry_commands = device_config.get(CONF_RETRY_COMMANDS, True)
        self.ipx = ipx
        self._transition = int(
            device_config.get(CONF_TRANSITION, DEFAULT_TRANSITION) * 1000
        )
        self._ipx_type = device_config[CONF_TYPE]
        self._component = device_config[CONF_COMPONENT]
        self._id = device_config.get(CONF_ID)
        self._ext_id = device_config.get(CONF_EXT_ID)
        self._ids = device_config.get(CONF_IDS, [])
        self._invert_value = device_config[CONF_INVERT_VALUE]

        self._attr_name: str = device_config[CONF_NAME]
        if suffix_name:
            self._attr_name = f"{self._attr_name} {suffix_name}"
        self._attr_device_class = device_config.get(CONF_DEVICE_CLASS)
        self._attr_native_unit_of_measurement = device_config.get(
            CONF_UNIT_OF_MEASUREMENT
        )
        self._attr_icon = device_config.get(CONF_ICON)
        self._attr_unique_id = "_".join(
            [DOMAIN, self.ipx.host, self._component, slugify(self._attr_name)]
        )

        configuration_url = f"http://{self.ipx.host}:{self.ipx.port}/admin/"
        if self._ipx_type == TYPE_RELAY:
            if self._id:
                if self._id <= 8:
                    configuration_url += "output.htm"
                else:
                    configuration_url += "8out.htm"
        elif self._ipx_type in [TYPE_X4VR, TYPE_X4VR_BSO]:
            configuration_url += "volet.htm"
        elif self._ipx_type in [TYPE_XPWM, TYPE_XPWM_RGB, TYPE_XPWM_RGBW]:
            configuration_url += "pwm.htm"
        elif self._ipx_type == TYPE_XDIMMER:
            configuration_url += "dimmer.htm"
        elif self._ipx_type == TYPE_VIRTUALOUT:
            configuration_url += "virtualout.htm"
        elif self._ipx_type == TYPE_VIRTUALIN:
            configuration_url += "virtualin.htm"
        elif self._ipx_type == TYPE_ANALOGIN:
            configuration_url += "analog.htm"
        elif self._ipx_type == TYPE_VIRTUALANALOGIN:
            configuration_url += "analogVirt.htm"
        elif self._ipx_type == TYPE_DIGITALIN:
            if self._id:
                if self._id <= 8:
                    configuration_url += "input.htm"
                else:
                    configuration_url += "24in.htm"
        elif self._ipx_type == TYPE_XTHL:
            configuration_url += "rht.htm"
        else:
            configuration_url += "periph.htm"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, slugify(device_config[CONF_NAME]))},
            "name": device_config[CONF_NAME],
            "manufacturer": "GCE",
            "model": "IPX800 V4",
            "via_device": (DOMAIN, self.ipx.host),
            "configuration_url": configuration_url,
        }

    @property
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """Require every field to be valid or within its bounded grace period."""
        return self.coordinator.fields_available(*self.required_keys)


class IpxDiagnosticEntity(CoordinatorEntity):
    """Diagnostic entity attached directly to the existing controller device."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, ipx: IPX800, coordinator: DataUpdateCoordinator, key: str
    ) -> None:
        """Initialize a controller diagnostic."""
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{DOMAIN}_{ipx.host}_diagnostic_{key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, ipx.host)}}

    @property
    def available(self) -> bool:
        """Return whether this field was present and valid in the last poll."""
        return (
            self.coordinator.last_update_success
            and self.system_data.get(self._key) is not None
        )

    @property
    def system_data(self) -> dict:
        """Return the latest system snapshot, including failed initial refreshes."""
        return self.coordinator.data or {}
