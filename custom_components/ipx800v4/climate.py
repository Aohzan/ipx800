"""Support for IPX800 V4 climates."""

import logging

from pypx800 import IPX800, X4FP, Ipx800RequestError, Relay

from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
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
    IPX_PRESET_AWAY,
    IPX_PRESET_COMFORT,
    IPX_PRESET_ECO,
    IPX_PRESET_NONE,
    PRESET_COMFORT_MINUS_1,
    PRESET_COMFORT_MINUS_2,
    TYPE_RELAY,
    TYPE_X4FP,
)
from .entity import IpxEntity

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IPX800 climates."""
    controller = hass.data[DOMAIN][entry.entry_id][CONTROLLER]
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    devices = hass.data[DOMAIN][entry.entry_id][CONF_DEVICES]["climate"]

    entities: list[ClimateEntity] = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_X4FP:
            entities.append(X4FPClimate(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_RELAY:
            entities.append(RelayClimate(device, controller, coordinator))

    async_add_entities(entities, True)


class X4FPClimate(IpxEntity, ClimateEntity):
    """Representation of a IPX Climate through X4FP."""

    _attr_translation_key = "ipx800v4_climate"

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the X4FPClimate."""
        super().__init__(device_config, ipx, coordinator)
        self.control = X4FP(ipx, self._ext_id, self._id)
        self._attr_supported_features = ClimateEntityFeature.PRESET_MODE
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
        self._attr_preset_modes = [
            PRESET_COMFORT,
            PRESET_ECO,
            PRESET_AWAY,
            PRESET_NONE,
            PRESET_COMFORT_MINUS_1,
            PRESET_COMFORT_MINUS_2,
        ]

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return current mode if heating or not."""
        if (
            self.coordinator.data[f"FP{self._ext_id} Zone {self._id}"]
            == IPX_PRESET_NONE
        ):
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current action if heating or not."""
        if (
            self.coordinator.data[f"FP{self._ext_id} Zone {self._id}"]
            == IPX_PRESET_NONE
        ):
            return HVACAction.OFF
        return HVACAction.HEATING

    @property
    def preset_mode(self) -> str | None:
        """Return current preset mode from IPX specific preset name."""
        switcher = {
            IPX_PRESET_NONE: PRESET_NONE,
            IPX_PRESET_ECO: PRESET_ECO,
            IPX_PRESET_AWAY: PRESET_AWAY,
            IPX_PRESET_COMFORT: PRESET_COMFORT,
            f"{IPX_PRESET_COMFORT} -1": PRESET_COMFORT_MINUS_1,
            f"{IPX_PRESET_COMFORT} -2": PRESET_COMFORT_MINUS_2,
        }
        return switcher.get(
            self.coordinator.data.get(f"FP{self._ext_id} Zone {self._id}")  # type: ignore[arg-type]
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        switcher = {
            PRESET_COMFORT: 0,
            PRESET_ECO: 1,
            PRESET_AWAY: 2,
            PRESET_NONE: 3,
            PRESET_COMFORT_MINUS_1: 4,
            PRESET_COMFORT_MINUS_2: 5,
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

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode."""
        try:
            if hvac_mode == HVACMode.HEAT:
                await self.control.set_mode(0)
            elif hvac_mode == HVACMode.OFF:
                await self.control.set_mode(3)
            else:
                _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
                return
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while set IPX800 climate hvac mode: %s", self.name
            )


class RelayClimate(IpxEntity, ClimateEntity):
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
        self._enable_turn_on_off_backwards_compatibility = False
        self._attr_supported_features = (
            ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
        self._attr_preset_modes = [PRESET_COMFORT, PRESET_ECO, PRESET_AWAY, PRESET_NONE]

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return current mode if heating or not."""
        if (
            int(self.coordinator.data[f"R{self._ids[0]}"]) == 0
            and int(self.coordinator.data[f"R{self._ids[1]}"]) == 1
        ):
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current action if heating or not."""
        if (
            int(self.coordinator.data[f"R{self._ids[0]}"]) == 0
            and int(self.coordinator.data[f"R{self._ids[1]}"]) == 1
        ):
            return HVACAction.OFF
        return HVACAction.HEATING

    @property
    def preset_mode(self) -> str | None:
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

    async def async_turn_off(self) -> None:
        """Turn the climate off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self) -> None:
        """Turn the climate on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode."""
        try:
            if hvac_mode == HVACMode.HEAT:
                await self.control_minus.off()
                await self.control_plus.off()
            elif hvac_mode == HVACMode.OFF:
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
