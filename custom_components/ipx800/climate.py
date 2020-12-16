"""Support for IPX800 climate."""
import logging

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_PRESET_MODE,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_IDLE,
    CURRENT_HVAC_OFF,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    PRESET_AWAY,
    PRESET_NONE,
    SUPPORT_PRESET_MODE,
)
from homeassistant.const import TEMP_CELSIUS
from pypx800 import *

from . import IpxController, IpxDevice
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Set up the IPX800 climates."""
    controller = hass.data[DOMAIN][config_entry.entry_id][CONTROLLER]
    devices = filter(
        lambda d: d[CONF_COMPONENT] == "climate", config_entry.data[CONF_DEVICES]
    )

    entities = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_X4FP:
            entities.append(X4FPClimate(device, controller))
        elif device.get(CONF_TYPE) == TYPE_RELAY:
            entities.append(RelayClimate(device, controller))

    async_add_entities(entities, True)


class X4FPClimate(IpxDevice, ClimateEntity):
    """Representation of a IPX Climate through X4FP."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.control = X4FP(controller.ipx, self._ext_id, self._id)

        self._supported_features |= SUPPORT_PRESET_MODE

    @property
    def temperature_unit(self):
        """Return Celcius indifferently since there is no temperature support."""
        return TEMP_CELSIUS

    @property
    def hvac_modes(self):
        return [HVAC_MODE_HEAT, HVAC_MODE_OFF]

    @property
    def hvac_mode(self):
        if self.coordinator.data[f"FP{self._ext_id} Zone {self._id}"] == "Arret":
            return HVAC_MODE_OFF
        return HVAC_MODE_HEAT

    @property
    def hvac_action(self):
        if self.coordinator.data[f"FP{self._ext_id} Zone {self._id}"] == "Arret":
            return CURRENT_HVAC_OFF
        return CURRENT_HVAC_HEAT

    @property
    def preset_modes(self):
        return ["Confort", "Eco", "Hors Gel", "Arret", "Confort -1", "Confort -2"]

    @property
    def preset_mode(self):
        return self.coordinator.data.get(f"FP{self._ext_id} Zone {self._id}")

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        switcher = {
            "Confort": 0,
            "Eco": 1,
            "Hors Gel": 2,
            "Arret": 3,
            "Confort -1": 4,
            "Confort -2": 5,
        }
        _LOGGER.debug(
            "set preset_mode to %s => id %s", preset_mode, switcher.get(preset_mode)
        )
        await self.hass.async_add_job(self.control.set_mode, switcher.get(preset_mode))
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set hvac mode."""
        if hvac_mode == HVAC_MODE_HEAT:
            await self.hass.async_add_job(self.control.set_mode, 0)
        elif hvac_mode == HVAC_MODE_OFF:
            await self.hass.async_add_job(self.control.set_mode, 3)
        else:
            _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
            return
        await self.coordinator.async_request_refresh()


class RelayClimate(IpxDevice, ClimateEntity):
    """Representation of a IPX Climate through 2 relais."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.control_minus = Relay(controller.ipx, self._ids[0])
        self.control_plus = Relay(controller.ipx, self._ids[1])

        self._supported_features |= SUPPORT_PRESET_MODE

    @property
    def temperature_unit(self):
        """Return Celcius indifferently since there is no temperature support."""
        return TEMP_CELSIUS

    @property
    def hvac_modes(self):
        return [HVAC_MODE_HEAT, HVAC_MODE_OFF]

    @property
    def hvac_mode(self):
        if (
            int(self.coordinator.data[f"R{self._ids[0]}"]) == 0
            and int(self.coordinator.data[f"R{self._ids[1]}"]) == 1
        ):
            return HVAC_MODE_OFF
        return HVAC_MODE_HEAT

    @property
    def hvac_action(self):
        if (
            int(self.coordinator.data[f"R{self._ids[0]}"]) == 0
            and int(self.coordinator.data[f"R{self._ids[1]}"]) == 1
        ):
            return CURRENT_HVAC_OFF
        return CURRENT_HVAC_HEAT

    @property
    def preset_modes(self):
        return ["Confort", "Eco", "Hors Gel", "Stop"]

    @property
    def preset_mode(self):
        state_minus = int(self.coordinator.data[f"R{self._ids[0]}"])
        state_plus = int(self.coordinator.data[f"R{self._ids[1]}"])
        switcher = {
            (0, 0): "Confort",
            (0, 1): "Stop",
            (1, 0): "Hors Gel",
            (1, 1): "Eco",
        }
        return switcher.get((state_minus, state_plus), "Inconnu")

    async def async_set_hvac_mode(self, hvac_mode):
        """Set hvac mode."""
        if hvac_mode == HVAC_MODE_HEAT:
            await self.hass.async_add_job(self.control.minus.off)
            await self.hass.async_add_job(self.control.plus.off)
        elif hvac_mode == HVAC_MODE_OFF:
            await self.hass.async_add_job(self.control.minus.off)
            await self.hass.async_add_job(self.control.plus.on)
        else:
            _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
            return
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        if preset_mode == "Confort":
            await self.hass.async_add_job(self.control.minus.off)
            await self.hass.async_add_job(self.control.plus.off)
        elif preset_mode == "Eco":
            await self.hass.async_add_job(self.control.minus.on)
            await self.hass.async_add_job(self.control.plus.on)
        elif preset_mode == "Hors Gel":
            await self.hass.async_add_job(self.control.minus.on)
            await self.hass.async_add_job(self.control.plus.off)
        else:
            await self.hass.async_add_job(self.control.minus.off)
            await self.hass.async_add_job(self.control.plus.on)
        await self.coordinator.async_request_refresh()
