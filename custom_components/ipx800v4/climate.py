"""Support for IPX800 V4 climates."""
import logging

from pypx800 import IPX800, X4FP, Ipx800RequestError, Relay

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_OFF,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_NONE,
    SUPPORT_PRESET_MODE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import TEMP_CELSIUS
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
    TYPE_X4FP,
)

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the IPX800 climates."""
    controller = hass.data[DOMAIN][entry.entry_id][CONTROLLER]
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    devices = hass.data[DOMAIN][entry.entry_id][CONF_DEVICES]["climate"]

    entities = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_X4FP:
            entities.append(X4FPClimate(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_RELAY:
            entities.append(RelayClimate(device, controller, coordinator))

    async_add_entities(entities, True)


class X4FPClimate(IpxDevice, ClimateEntity):
    """Representation of a IPX Climate through X4FP."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the X4FPClimate."""
        super().__init__(device_config, ipx, coordinator)
        self.control = X4FP(ipx, self._ext_id, self._id)

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_PRESET_MODE

    @property
    def temperature_unit(self) -> str:
        """Return Celsius indifferently since there is no temperature support."""
        return TEMP_CELSIUS

    @property
    def hvac_modes(self) -> list:
        """Return modes."""
        return [HVAC_MODE_HEAT, HVAC_MODE_OFF]

    @property
    def hvac_mode(self) -> str:
        """Return current mode if heating or not."""
        if self.coordinator.data[f"FP{self._ext_id} Zone {self._id}"] == PRESET_NONE:
            return HVAC_MODE_OFF
        return HVAC_MODE_HEAT

    @property
    def hvac_action(self) -> str:
        """Return current action if heating or not."""
        if self.coordinator.data[f"FP{self._ext_id} Zone {self._id}"] == PRESET_NONE:
            return CURRENT_HVAC_OFF
        return CURRENT_HVAC_HEAT

    @property
    def preset_modes(self) -> str:
        """Return all preset modes."""
        return [
            PRESET_COMFORT,
            PRESET_ECO,
            PRESET_AWAY,
            PRESET_NONE,
            f"{PRESET_COMFORT} -1",
            f"{PRESET_COMFORT} -2",
        ]

    @property
    def preset_mode(self) -> str:
        """Return current preset mode."""
        return self.coordinator.data.get(f"FP{self._ext_id} Zone {self._id}")

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        switcher = {
            PRESET_COMFORT: 0,
            PRESET_ECO: 1,
            PRESET_AWAY: 2,
            PRESET_NONE: 3,
            f"{PRESET_COMFORT} -1": 4,
            f"{PRESET_COMFORT} -2": 5,
        }
        _LOGGER.debug(
            "set preset_mode to %s => id %s", preset_mode, switcher.get(preset_mode)
        )
        try:
            await self.control.set_mode(switcher.get(preset_mode))
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while set IPX800 climate preset mode: %s", self.name
            )

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set hvac mode."""
        try:
            if hvac_mode == HVAC_MODE_HEAT:
                await self.control.set_mode(0)
            elif hvac_mode == HVAC_MODE_OFF:
                await self.control.set_mode(3)
            else:
                _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
                return
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while set IPX800 climate hvac mode: %s", self.name
            )


class RelayClimate(IpxDevice, ClimateEntity):
    """Representation of a IPX Climate through 2 relais."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the RelayClimate."""
        super().__init__(device_config, ipx, coordinator)
        self.control_minus = Relay(ipx, self._ids[0])
        self.control_plus = Relay(ipx, self._ids[1])

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_PRESET_MODE

    @property
    def temperature_unit(self) -> str:
        """Return Celsius indifferently since there is no temperature support."""
        return TEMP_CELSIUS

    @property
    def hvac_modes(self) -> list:
        """Return modes."""
        return [HVAC_MODE_HEAT, HVAC_MODE_OFF]

    @property
    def hvac_mode(self) -> str:
        """Return current mode if heating or not."""
        if (
            int(self.coordinator.data[f"R{self._ids[0]}"]) == 0
            and int(self.coordinator.data[f"R{self._ids[1]}"]) == 1
        ):
            return HVAC_MODE_OFF
        return HVAC_MODE_HEAT

    @property
    def hvac_action(self) -> str:
        """Return current action if heating or not."""
        if (
            int(self.coordinator.data[f"R{self._ids[0]}"]) == 0
            and int(self.coordinator.data[f"R{self._ids[1]}"]) == 1
        ):
            return CURRENT_HVAC_OFF
        return CURRENT_HVAC_HEAT

    @property
    def preset_modes(self) -> str:
        """Return all preset modes."""
        return [PRESET_COMFORT, PRESET_ECO, PRESET_AWAY, PRESET_NONE]

    @property
    def preset_mode(self) -> str:
        """Return current preset mode from 2 relay states."""
        state_minus = int(self.coordinator.data[f"R{self._ids[0]}"])
        state_plus = int(self.coordinator.data[f"R{self._ids[1]}"])
        switcher = {
            (0, 0): PRESET_COMFORT,
            (0, 1): PRESET_NONE,
            (1, 0): PRESET_AWAY,
            (1, 1): PRESET_ECO,
        }
        return switcher.get((state_minus, state_plus))

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set hvac mode."""
        try:
            if hvac_mode == HVAC_MODE_HEAT:
                await self.control_minus.off()
                await self.control_plus.off()
            elif hvac_mode == HVAC_MODE_OFF:
                await self.control_minus.off()
                await self.control_plus.on()
            else:
                _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
                return
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while set IPX800 climate hvac mode: %s", self.name
            )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set target preset mode."""
        try:
            if preset_mode == PRESET_COMFORT:
                await self.control_minus.off()
                await self.control_plus.off()
            elif preset_mode == PRESET_ECO:
                await self.control_minus.on()
                await self.control_plus.on()
            elif preset_mode == PRESET_AWAY:
                await self.control_minus.on()
                await self.control_plus.off()
            else:
                await self.control_minus.off()
                await self.control_plus.on()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while set IPX800 climate preset mode: %s", self.name
            )
