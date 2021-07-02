"""Support for IPX800 V4 lights."""
import logging
from typing import List

from pypx800 import IPX800, XPWM, Ipx800RequestError, Relay, XDimmer

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_TRANSITION,
    COLOR_MODE_BRIGHTNESS,
    COLOR_MODE_ONOFF,
    COLOR_MODE_RGB,
    COLOR_MODE_RGBW,
    SUPPORT_TRANSITION,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import IpxDevice
from .const import (
    CONF_DEFAULT_BRIGHTNESS,
    CONF_DEVICES,
    CONF_TRANSITION,
    CONF_TYPE,
    CONTROLLER,
    COORDINATOR,
    DEFAULT_TRANSITION,
    DOMAIN,
    GLOBAL_PARALLEL_UPDATES,
    TYPE_RELAY,
    TYPE_XDIMMER,
    TYPE_XPWM,
    TYPE_XPWM_RGB,
    TYPE_XPWM_RGBW,
)

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


def scaleto255(value):
    """Scale to Home-Assistant value."""
    return max(0, min(255, round((value * 255.0) / 100.0)))


def scaleto100(value):
    """Scale to IPX800 value."""
    return max(0, min(100, round((value * 100.0) / 255.0)))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the IPX800 lights."""
    controller = hass.data[DOMAIN][entry.entry_id][CONTROLLER]
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    devices = hass.data[DOMAIN][entry.entry_id][CONF_DEVICES]["light"]

    entities: List[LightEntity] = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_RELAY:
            entities.append(RelayLight(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_XDIMMER:
            entities.append(XDimmerLight(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_XPWM:
            entities.append(XPWMLight(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_XPWM_RGB:
            entities.append(XPWMRGBLight(device, controller, coordinator))
        elif device.get(CONF_TYPE) == TYPE_XPWM_RGBW:
            entities.append(XPWMRGBWLight(device, controller, coordinator))

    async_add_entities(entities, True)


class RelayLight(IpxDevice, LightEntity):
    """Representation of a IPX Light through relay."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ):
        """Initialize the RelayLight."""
        super().__init__(device_config, ipx, coordinator)
        self.control = Relay(ipx, self._id)

    @property
    def supported_color_modes(self) -> set:
        """Return supported color modes."""
        return {COLOR_MODE_ONOFF}

    @property
    def color_mode(self) -> str:
        """Return the color mode of the light."""
        return COLOR_MODE_ONOFF

    @property
    def is_on(self) -> bool:
        """Return if the light is on."""
        return self.coordinator.data[f"R{self._id}"] == 1

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the light."""
        try:
            await self.control.on()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turning on IPX800 light: %s", self.name
            )
            return None

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the light."""
        try:
            await self.control.off()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turning off IPX800 light: %s", self.name
            )
            return None

    async def async_toggle(self, **kwargs) -> None:
        """Toggle the light."""
        try:
            await self.control.toggle()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while toggle IPX800 light: %s", self.name)
            return None


class XDimmerLight(IpxDevice, LightEntity):
    """Representation of a IPX Light through X-Dimmer."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ):
        """Initialize the class XDimmerLight."""
        super().__init__(device_config, ipx, coordinator)
        self.control = XDimmer(ipx, self._id)
        self._brightness = None
        self._transition = device_config.get(CONF_TRANSITION, DEFAULT_TRANSITION)

    @property
    def supported_color_modes(self) -> set:
        """Return supported color modes."""
        return {COLOR_MODE_BRIGHTNESS}

    @property
    def supported_features(self) -> int:
        """Return supported features."""
        return SUPPORT_TRANSITION

    @property
    def color_mode(self) -> str:
        """Return the color mode of the light."""
        return COLOR_MODE_BRIGHTNESS

    @property
    def is_on(self) -> bool:
        """Return if the light is on."""
        return self.coordinator.data[f"G{self._id}"]["Etat"] == "ON"

    @property
    def brightness(self) -> int:
        """Return the brightness of the light."""
        return scaleto255(self.coordinator.data[f"G{self._id}"]["Valeur"])

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the light."""
        try:
            if ATTR_TRANSITION in kwargs:
                self._transition = kwargs[ATTR_TRANSITION]
            if ATTR_BRIGHTNESS in kwargs:
                self._brightness = kwargs[ATTR_BRIGHTNESS]
                await self.control.set_level(
                    scaleto100(self._brightness), self._transition * 1000
                )
            else:
                await self.control.on(self._transition * 1000)
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turning on IPX800 light: %s", self.name
            )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the light."""
        try:
            if ATTR_TRANSITION in kwargs:
                self._transition = kwargs[ATTR_TRANSITION]
            await self.control.off(self._transition * 1000)
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turning off IPX800 light: %s", self.name
            )

    async def async_toggle(self, **kwargs) -> None:
        """Toggle the light."""
        try:
            if ATTR_TRANSITION in kwargs:
                self._transition = kwargs[ATTR_TRANSITION]
            await self.control.toggle(self._transition * 1000)
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while toggle IPX800 light: %s", self.name)


class XPWMLight(IpxDevice, LightEntity):
    """Representation of a IPX Light through X-PWM single channel."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ):
        """Initialize the XPWMLight."""
        super().__init__(device_config, ipx, coordinator)
        self.control = XPWM(ipx, self._id)

        self._brightness = None
        self._default_brightness = device_config.get(CONF_DEFAULT_BRIGHTNESS, 100)
        self._transition = device_config.get(CONF_TRANSITION, DEFAULT_TRANSITION)

    @property
    def supported_color_modes(self) -> set:
        """Return supported color modes."""
        return {COLOR_MODE_BRIGHTNESS}

    @property
    def supported_features(self) -> int:
        """Return supported features."""
        return SUPPORT_TRANSITION

    @property
    def color_mode(self) -> str:
        """Return the color mode of the light."""
        return COLOR_MODE_BRIGHTNESS

    @property
    def is_on(self) -> bool:
        """Return if the light is on."""
        return self.coordinator.data[f"PWM{self._id}"] > 0

    @property
    def brightness(self) -> int:
        """Return the brightness of the light."""
        return scaleto255(self.coordinator.data[f"PWM{self._id}"])

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the light."""
        try:
            if ATTR_TRANSITION in kwargs:
                self._transition = kwargs[ATTR_TRANSITION]
            if ATTR_BRIGHTNESS in kwargs:
                self._brightness = kwargs[ATTR_BRIGHTNESS]
                await self.control.set_level(
                    scaleto100(self._brightness), self._transition * 1000
                )
            else:
                await self.control.set_level(
                    self._default_brightness, self._transition * 1000
                )
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turning on IPX800 light: %s", self.name
            )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the light."""
        try:
            if ATTR_TRANSITION in kwargs:
                self._transition = kwargs[ATTR_TRANSITION]
            await self.control.off(self._transition * 1000)
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turning off IPX800 light: %s", self.name
            )

    async def async_toggle(self, **kwargs) -> None:
        """Toggle the light."""
        try:
            if ATTR_TRANSITION in kwargs:
                self._transition = kwargs[ATTR_TRANSITION]
            await self.control.toggle(self._transition * 1000)
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while toggle IPX800 light: %s", self.name)


class XPWMRGBLight(IpxDevice, LightEntity):
    """Representation of a RGB light through 3 X-PWM channels."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ):
        """Initialize the XPWMRGBLight."""
        super().__init__(device_config, ipx, coordinator)
        self.xpwm_rgb_r = XPWM(ipx, self._ids[0])
        self.xpwm_rgb_g = XPWM(ipx, self._ids[1])
        self.xpwm_rgb_b = XPWM(ipx, self._ids[2])

        self._brightness = None
        self._default_brightness = device_config.get(CONF_DEFAULT_BRIGHTNESS, 100)
        self._transition = device_config.get(CONF_TRANSITION, DEFAULT_TRANSITION)

    @property
    def supported_color_modes(self) -> set:
        """Return supported color modes."""
        return {COLOR_MODE_RGB}

    @property
    def supported_features(self) -> int:
        """Return supported features."""
        return SUPPORT_TRANSITION

    @property
    def color_mode(self) -> str:
        """Return the color mode of the light."""
        return COLOR_MODE_RGB

    @property
    def is_on(self) -> bool:
        """Return if at least a level in on."""
        return any(i > 0 for i in self.rgb_color)

    @property
    def brightness(self) -> int:
        """Return the brightness from levels."""
        return max(self.rgb_color)

    @property
    def rgb_color(self):
        """Return the RGB color from RGB levels."""
        level_r = scaleto255(self.coordinator.data[f"PWM{self._ids[0]}"])
        level_g = scaleto255(self.coordinator.data[f"PWM{self._ids[1]}"])
        level_b = scaleto255(self.coordinator.data[f"PWM{self._ids[2]}"])
        return (level_r, level_g, level_b)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the light."""
        try:
            if ATTR_TRANSITION in kwargs:
                self._transition = kwargs[ATTR_TRANSITION]
            if ATTR_RGB_COLOR in kwargs:
                colors = kwargs[ATTR_RGB_COLOR]
                await self.xpwm_rgb_r.set_level(
                    scaleto100(colors[0]), self._transition * 1000
                )
                await self.xpwm_rgb_g.set_level(
                    scaleto100(colors[1]), self._transition * 1000
                )
                await self.xpwm_rgb_b.set_level(
                    scaleto100(colors[2]), self._transition * 1000
                )
            elif ATTR_BRIGHTNESS in kwargs:
                self._brightness = kwargs[ATTR_BRIGHTNESS]
                if self.is_on:
                    await self.xpwm_rgb_r.set_level(
                        self.coordinator.data[f"PWM{self._ids[0]}"]
                        * self._brightness
                        / 100,
                        self._transition * 1000,
                    )
                    await self.xpwm_rgb_g.set_level(
                        self.coordinator.data[f"PWM{self._ids[1]}"]
                        * self._brightness
                        / 100,
                        self._transition * 1000,
                    )
                    await self.xpwm_rgb_b.set_level(
                        self.coordinator.data[f"PWM{self._ids[2]}"]
                        * self._brightness
                        / 100,
                        self._transition * 1000,
                    )
                else:
                    await self.xpwm_rgb_r.set_level(
                        scaleto100(self._brightness),
                        self._transition * 1000,
                    )
                    await self.xpwm_rgb_g.set_level(
                        scaleto100(self._brightness),
                        self._transition * 1000,
                    )
                    await self.xpwm_rgb_b.set_level(
                        scaleto100(self._brightness),
                        self._transition * 1000,
                    )
            else:
                await self.xpwm_rgb_r.set_level(
                    self._default_brightness, self._transition * 1000
                )
                await self.xpwm_rgb_g.set_level(
                    self._default_brightness, self._transition * 1000
                )
                await self.xpwm_rgb_b.set_level(
                    self._default_brightness, self._transition * 1000
                )
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turn off IPX800 light: %s", self.name
            )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the light."""
        try:
            if ATTR_TRANSITION in kwargs:
                self._transition = kwargs[ATTR_TRANSITION] * 1000
            await self.xpwm_rgb_r.off(self._transition * 1000)
            await self.xpwm_rgb_g.off(self._transition * 1000)
            await self.xpwm_rgb_b.off(self._transition * 1000)
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turn off IPX800 light: %s", self.name
            )


class XPWMRGBWLight(IpxDevice, LightEntity):
    """Representation of a RGBW light through 4 X-PWM channels."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ):
        """Initialize the XPWMRGBWLight."""
        super().__init__(device_config, ipx, coordinator)
        self.xpwm_rgbw_r = XPWM(ipx, self._ids[0])
        self.xpwm_rgbw_g = XPWM(ipx, self._ids[1])
        self.xpwm_rgbw_b = XPWM(ipx, self._ids[2])
        self.xpwm_rgbw_w = XPWM(ipx, self._ids[3])

        self._brightness = None
        self._default_brightness = device_config.get(CONF_DEFAULT_BRIGHTNESS, 100)
        self._transition = device_config.get(CONF_TRANSITION, DEFAULT_TRANSITION)

    @property
    def supported_color_modes(self) -> set:
        """Return supported color modes."""
        return {COLOR_MODE_RGBW}

    @property
    def supported_features(self) -> int:
        """Return supported features."""
        return SUPPORT_TRANSITION

    @property
    def color_mode(self) -> str:
        """Return the color mode of the light."""
        return COLOR_MODE_RGBW

    @property
    def is_on(self) -> bool:
        """Return if at least a level in on."""
        return any(i > 0 for i in self.rgbw_color)

    @property
    def brightness(self) -> int:
        """Return the brightness from levels."""
        return max(self.rgbw_color)

    @property
    def rgbw_color(self):
        """Return the RGB color from RGB levels."""
        level_r = scaleto255(self.coordinator.data[f"PWM{self._ids[0]}"])
        level_g = scaleto255(self.coordinator.data[f"PWM{self._ids[1]}"])
        level_b = scaleto255(self.coordinator.data[f"PWM{self._ids[2]}"])
        level_w = scaleto255(self.coordinator.data[f"PWM{self._ids[3]}"])
        return (level_r, level_g, level_b, level_w)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the light."""
        try:
            if ATTR_TRANSITION in kwargs:
                self._transition = kwargs[ATTR_TRANSITION]

            if ATTR_RGBW_COLOR in kwargs:
                colors = kwargs[ATTR_RGBW_COLOR]
                # if only rgb color have been set
                await self.xpwm_rgbw_r.set_level(
                    scaleto100(colors[0]), self._transition * 1000
                )
                await self.xpwm_rgbw_g.set_level(
                    scaleto100(colors[1]), self._transition * 1000
                )
                await self.xpwm_rgbw_b.set_level(
                    scaleto100(colors[2]), self._transition * 1000
                )
                await self.xpwm_rgbw_w.set_level(
                    scaleto100(colors[3]), self._transition * 1000
                )
            elif ATTR_BRIGHTNESS in kwargs:
                self._brightness = kwargs[ATTR_BRIGHTNESS]
                if self.is_on:
                    await self.xpwm_rgbw_r.set_level(
                        self.coordinator.data[f"PWM{self._ids[0]}"]
                        * self._brightness
                        / 100,
                        self._transition * 1000,
                    )
                    await self.xpwm_rgbw_g.set_level(
                        self.coordinator.data[f"PWM{self._ids[1]}"]
                        * self._brightness
                        / 100,
                        self._transition * 1000,
                    )
                    await self.xpwm_rgbw_b.set_level(
                        self.coordinator.data[f"PWM{self._ids[2]}"]
                        * self._brightness
                        / 100,
                        self._transition * 1000,
                    )
                    await self.xpwm_rgbw_w.set_level(
                        self.coordinator.data[f"PWM{self._ids[3]}"]
                        * self._brightness
                        / 100,
                        self._transition * 1000,
                    )
                else:
                    await self.xpwm_rgbw_w.set_level(
                        scaleto100(self._brightness),
                        self._transition * 1000,
                    )
            else:
                await self.xpwm_rgbw_w.set_level(
                    self._default_brightness, self._transition * 1000
                )
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turn off IPX800 light: %s", self.name
            )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the light."""
        try:
            if ATTR_TRANSITION in kwargs:
                self._transition = kwargs[ATTR_TRANSITION]
            await self.xpwm_rgbw_w.off(self._transition * 1000)
            await self.xpwm_rgbw_r.off(self._transition * 1000)
            await self.xpwm_rgbw_g.off(self._transition * 1000)
            await self.xpwm_rgbw_b.off(self._transition * 1000)
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while turn off IPX800 light: %s", self.name
            )
