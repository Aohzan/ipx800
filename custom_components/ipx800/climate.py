"""Support for IPX800 climate."""
import logging

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity import Entity
from homeassistant.const import TEMP_CELSIUS
from homeassistant.components.climate import (
    ClimateEntity,
)
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

from pypx800 import *
from .device import *
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the IPX800 climate."""
    _LOGGER.error("setup climate")
    async_add_entities(
        [
            X4FPClimate(device)
            for device in (
                item
                for item in discovery_info
                if item.get("config").get(CONF_TYPE) == TYPE_X4FP
            )
        ],
        True,
    )

    async_add_entities(
        [
            RelayClimate(device)
            for device in (
                item
                for item in discovery_info
                if item.get("config").get(CONF_TYPE) == TYPE_RELAY
            )
        ],
        True,
    )


class X4FPClimate(IpxDevice, ClimateEntity):
    """Representation of a IPX Climate through X4FP."""

    def __init__(self, ipx_device):
        super().__init__(ipx_device)
        self.control = X4FP(self.controller.ipx, self._ext_id, self._id)

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
        if int(self.coordinator.data[f"FP{self._ext_id} Zone {self._id}"]) == 3:
            return HVAC_MODE_OFF
        return HVAC_MODE_HEAT

    @property
    def hvac_action(self):
        if int(self.coordinator.data[f"FP{self._ext_id} Zone {self._id}"]) == 3:
            return CURRENT_HVAC_OFF
        return CURRENT_HVAC_HEAT

    @property
    def preset_modes(self):
        return ['Confort',
                'Eco',
                'Hors Gel',
                'Stop',
                'Confort -1',
                'Confort -2']

    @property
    def preset_mode(self):
        state = int(self.coordinator.data[f"FP{self._ext_id} Zone {self._id}"])
        switcher = {
            0: 'Confort',
            1: 'Eco',
            2: 'Hors Gel',
            3: 'Stop',
            4: 'Confort -1',
            5: 'Confort -2'
        }
        _LOGGER.debug("preset_mode: id %s => %s", state,
                      switcher.get(state, "Inconnu"))
        return switcher.get(state, "Inconnu")

    def set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        switcher = {
            'Confort': 0,
            'Eco': 1,
            'Hors Gel': 2,
            'Stop': 3,
            'Confort -1': 4,
            'Confort -2': 5
        }
        _LOGGER.debug("set preset_mode to %s => id %s",
                      preset_mode, switcher.get(preset_mode))
        self.control.set_mode(switcher.get(preset_mode))

    def set_hvac_mode(self, hvac_mode):
        """Set hvac mode."""
        if hvac_mode == HVAC_MODE_HEAT:
            self.control.set_mode(0)
        elif hvac_mode == HVAC_MODE_OFF:
            self.control.set_mode(3)
        else:
            _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
            return


class RelayClimate(IpxDevice, ClimateEntity):
    """Representation of a IPX Climate through 2 relais."""

    def __init__(self, ipx_device):
        super().__init__(ipx_device)
        self.control_minus = Relay(self.controller.ipx, self._ids[0])
        self.control_plus = Relay(self.controller.ipx, self._ids[1])

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
        if int(self.coordinator.data[f"R{self._ids[0]}"]) == 0 and int(self.coordinator.data[f"R{self._ids[1]}"]) == 1:
            return HVAC_MODE_OFF
        return HVAC_MODE_HEAT

    @property
    def hvac_action(self):
        if int(self.coordinator.data[f"R{self._ids[0]}"]) == 0 and int(self.coordinator.data[f"R{self._ids[1]}"]) == 1:
            return CURRENT_HVAC_OFF
        return CURRENT_HVAC_HEAT

    @property
    def preset_modes(self):
        return ['Confort',
                'Eco',
                'Hors Gel',
                'Stop']

    @property
    def preset_mode(self):
        state_minus = int(self.coordinator.data[f"R{self._ids[0]}"])
        state_plus = int(self.coordinator.data[f"R{self._ids[1]}"])
        switcher = {
            (0, 0): 'Confort',
            (0, 1): 'Stop',
            (1, 0): 'Hors Gel',
            (1, 1): 'Eco'
        }
        return switcher.get((state_minus, state_plus), "Inconnu")

    def set_hvac_mode(self, hvac_mode):
        """Set hvac mode."""
        if hvac_mode == HVAC_MODE_HEAT:
            self.control_minus.off()
            self.control_plus.off()
        elif hvac_mode == HVAC_MODE_OFF:
            self.control_minus.off()
            self.control_plus.on()
        else:
            _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
            return

    def set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        if preset_mode == "Confort":
            self.control_minus.off()
            self.control_plus.off()
        elif preset_mode == "Eco":
            self.control_minus.on()
            self.control_plus.on()
        elif preset_mode == "Hors Gel":
            self.control_minus.on()
            self.control_plus.off()
        else:
            self.control_minus.off()
            self.control_plus.on()
