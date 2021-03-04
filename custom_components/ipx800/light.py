"""Support for IPX800 lights."""
import logging

from pypx800 import *

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    ATTR_WHITE_VALUE,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_TRANSITION,
    SUPPORT_WHITE_VALUE,
    LightEntity,
)
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_ICON,
    CONF_NAME,
    CONF_UNIT_OF_MEASUREMENT,
)
import homeassistant.util.color as color_util

from . import IpxController, IpxDevice
from .const import *

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


def scaleto255(value):
    return max(0, min(255, round((value * 255.0) / 100.0)))


def scaleto100(value):
    return max(0, min(100, round((value * 100.0) / 255.0)))


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Set up the IPX800 lights."""
    controller = hass.data[DOMAIN][config_entry.entry_id][CONTROLLER]
    devices = filter(
        lambda d: d[CONF_COMPONENT] == "light", config_entry.data[CONF_DEVICES]
    )

    entities = []

    for device in devices:
        if device.get(CONF_TYPE) == TYPE_RELAY:
            entities.append(RelayLight(device, controller))
        elif device.get(CONF_TYPE) == TYPE_XDIMMER:
            entities.append(XDimmerLight(device, controller))
        elif device.get(CONF_TYPE) == TYPE_XPWM:
            entities.append(XPWMLight(device, controller))
        elif device.get(CONF_TYPE) == TYPE_XPWM_RGB:
            entities.append(XPWMRGBLight(device, controller))
        elif device.get(CONF_TYPE) == TYPE_XPWM_RGBW:
            entities.append(XPWMRGBWLight(device, controller))

    async_add_entities(entities, True)


class RelayLight(IpxDevice, LightEntity):
    """Representation of a IPX Light through relay."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.control = Relay(controller.ipx, self._id)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data[f"R{self._id}"] == 1

    def turn_on(self, **kwargs):
        self.control.on()

    def turn_off(self, **kwargs):
        self.control.off()

    def toggle(self, **kwargs):
        self.control.toggle()


class XDimmerLight(IpxDevice, LightEntity):
    """Representation of a IPX Light through X-Dimmer."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.control = XDimmer(controller.ipx, self._id)

        self._brightness = None
        self._supported_features |= SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION

    @property
    def is_on(self) -> bool:
        return self.coordinator.data[f"G{self._id}"]["Etat"] == "ON"

    @property
    def brightness(self) -> int:
        return scaleto255(self.coordinator.data[f"G{self._id}"]["Valeur"])

    def turn_on(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = int(kwargs.get(ATTR_TRANSITION) * 1000)
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
            self.control.set_level(scaleto100(self._brightness), self._transition)
        else:
            self.control.on(self._transition)

    def turn_off(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = int(kwargs.get(ATTR_TRANSITION) * 1000)
        self.control.off(self._transition)

    def toggle(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = int(kwargs.get(ATTR_TRANSITION) * 1000)
        self.control.toggle(self._transition)


class XPWMLight(IpxDevice, LightEntity):
    """Representation of a IPX Light through X-PWM single channel."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.control = XPWM(controller.ipx, self._id)

        self._brightness = None
        self._supported_features |= SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION

    @property
    def is_on(self) -> bool:
        return self.coordinator.data[f"PWM{self._id}"] > 0

    @property
    def brightness(self) -> int:
        return scaleto255(self.coordinator.data[f"PWM{self._id}"])

    def turn_on(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = int(kwargs.get(ATTR_TRANSITION) * 1000)
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
            self.control.set_level(scaleto100(self._brightness), self._transition)
        else:
            self.control.on(self._transition)

    def turn_off(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = int(kwargs.get(ATTR_TRANSITION) * 1000)
        self.control.off(self._transition)

    def toggle(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = int(kwargs.get(ATTR_TRANSITION) * 1000)
        self.control.toggle(self._transition)


class XPWMRGBLight(IpxDevice, LightEntity):
    """Representation of a RGB light through 3 X-PWM channels."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.xpwm_rgb_r = XPWM(controller.ipx, self._ids[0])
        self.xpwm_rgb_g = XPWM(controller.ipx, self._ids[1])
        self.xpwm_rgb_b = XPWM(controller.ipx, self._ids[2])

        self._brightness = None
        self._rgb_color = None
        self._supported_features |= (
            SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION | SUPPORT_COLOR
        )

    @property
    def is_on(self) -> bool:
        level_r = scaleto255(self.coordinator.data[f"PWM{self._ids[0]}"])
        level_g = scaleto255(self.coordinator.data[f"PWM{self._ids[1]}"])
        level_b = scaleto255(self.coordinator.data[f"PWM{self._ids[2]}"])
        return level_r > 0 or level_b > 0 or level_g > 0

    @property
    def brightness(self):
        level_r = scaleto255(self.coordinator.data[f"PWM{self._ids[0]}"])
        level_g = scaleto255(self.coordinator.data[f"PWM{self._ids[1]}"])
        level_b = scaleto255(self.coordinator.data[f"PWM{self._ids[2]}"])
        return 0.2126 * level_r + 0.7152 * level_g + 0.0722 * level_b

    @property
    def rgb_color(self):
        level_r = scaleto255(self.coordinator.data[f"PWM{self._ids[0]}"])
        level_g = scaleto255(self.coordinator.data[f"PWM{self._ids[1]}"])
        level_b = scaleto255(self.coordinator.data[f"PWM{self._ids[2]}"])
        return [level_r, level_g, level_b]

    def turn_on(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = int(kwargs.get(ATTR_TRANSITION) * 1000)

        if ATTR_RGB_COLOR in kwargs or ATTR_HS_COLOR in kwargs:
            if ATTR_RGB_COLOR in kwargs:
                self._rgb_color = kwargs.get(ATTR_RGB_COLOR)
            elif ATTR_HS_COLOR in kwargs:
                self._rgb_color = color_util.color_hs_to_RGB(*kwargs.get(ATTR_HS_COLOR))
            self.xpwm_rgb_r.set_level(
                scaleto100(self._rgb_color[0]),
                self._transition,
            )
            self.xpwm_rgb_g.set_level(
                scaleto100(self._rgb_color[1]),
                self._transition,
            )
            self.xpwm_rgb_b.set_level(
                scaleto100(self._rgb_color[2]),
                self._transition,
            )

        elif ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs.get(ATTR_BRIGHTNESS)
            if self.is_on:
                self.xpwm_rgb_r.set_level(
                    scaleto100(self.xpwm_rgb_r.level * self._brightness / 255),
                    self._transition,
                )
                self.xpwm_rgb_g.set_level(
                    scaleto100(self.xpwm_rgb_g.level * self._brightness / 255),
                    self._transition,
                )
                self.xpwm_rgb_b.set_level(
                    scaleto100(self.xpwm_rgb_b.level * self._brightness / 255),
                    self._transition,
                )
            else:
                self.xpwm_rgb_r.set_level(
                    scaleto100(self._brightness),
                    self._transition,
                )
                self.xpwm_rgb_g.set_level(
                    scaleto100(self._brightness),
                    self._transition,
                )
                self.xpwm_rgb_b.set_level(
                    scaleto100(self._brightness),
                    self._transition,
                )
        else:
            self.xpwm_rgb_r.on(self._transition)
            self.xpwm_rgb_g.on(self._transition)
            self.xpwm_rgb_b.on(self._transition)

    def turn_off(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = int(kwargs.get(ATTR_TRANSITION) * 1000)
        self.xpwm_rgb_r.off(self._transition)
        self.xpwm_rgb_g.off(self._transition)
        self.xpwm_rgb_b.off(self._transition)


class XPWMRGBWLight(IpxDevice, LightEntity):
    """Representation of a RGBW light through 4 X-PWM channels."""

    def __init__(self, device_config, controller: IpxController):
        super().__init__(device_config, controller)
        self.xpwm_rgbw_r = XPWM(controller.ipx, self._ids[0])
        self.xpwm_rgbw_g = XPWM(controller.ipx, self._ids[1])
        self.xpwm_rgbw_b = XPWM(controller.ipx, self._ids[2])
        self.xpwm_rgbw_w = XPWM(controller.ipx, self._ids[3])

        self._brightness = None
        self._rgb_color = None
        self._white_value = None
        self._supported_features |= (
            SUPPORT_BRIGHTNESS
            | SUPPORT_TRANSITION
            | SUPPORT_COLOR
            | SUPPORT_WHITE_VALUE
        )

    @property
    def is_on(self) -> bool:
        level_r = scaleto255(self.coordinator.data[f"PWM{self._ids[0]}"])
        level_g = scaleto255(self.coordinator.data[f"PWM{self._ids[1]}"])
        level_b = scaleto255(self.coordinator.data[f"PWM{self._ids[2]}"])
        level_w = scaleto255(self.coordinator.data[f"PWM{self._ids[3]}"])
        return level_r > 0 or level_b > 0 or level_g > 0 or level_w > 0

    @property
    def brightness(self):
        level_r = scaleto255(self.coordinator.data[f"PWM{self._ids[0]}"])
        level_g = scaleto255(self.coordinator.data[f"PWM{self._ids[1]}"])
        level_b = scaleto255(self.coordinator.data[f"PWM{self._ids[2]}"])
        level_w = scaleto255(self.coordinator.data[f"PWM{self._ids[3]}"])
        if level_r > 0 or level_b > 0 or level_g > 0:
            self._brightness = 0.2126 * level_r + 0.7152 * level_g + 0.0722 * level_b
        else:
            self._brightness = level_w
        return self._brightness

    @property
    def rgb_color(self):
        level_r = scaleto255(self.coordinator.data[f"PWM{self._ids[0]}"])
        level_g = scaleto255(self.coordinator.data[f"PWM{self._ids[1]}"])
        level_b = scaleto255(self.coordinator.data[f"PWM{self._ids[2]}"])
        return [level_r, level_g, level_b]

    @property
    def white_value(self):
        return scaleto255(self.coordinator.data[f"PWM{self._ids[3]}"])

    def turn_on(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = int(kwargs.get(ATTR_TRANSITION) * 1000)

        if ATTR_RGB_COLOR in kwargs or ATTR_HS_COLOR in kwargs:
            if ATTR_RGB_COLOR in kwargs:
                self._rgb_color = kwargs.get(ATTR_RGB_COLOR)
            elif ATTR_HS_COLOR in kwargs:
                self._rgb_color = color_util.color_hs_to_RGB(*kwargs.get(ATTR_HS_COLOR))
            rgbw = color_util.color_rgb_to_rgbw(*self._rgb_color)
            self.xpwm_rgbw_r.set_level(scaleto100(rgbw[0]), self._transition)
            self.xpwm_rgbw_g.set_level(scaleto100(rgbw[1]), self._transition)
            self.xpwm_rgbw_b.set_level(scaleto100(rgbw[2]), self._transition)
            self.xpwm_rgbw_w.set_level(scaleto100(rgbw[3]), self._transition)
        elif ATTR_WHITE_VALUE in kwargs:
            self._white_value = kwargs.get(ATTR_WHITE_VALUE)
            self.xpwm_rgbw_w.set_level(scaleto100(self._white_value), self._transition)
        elif ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs.get(ATTR_BRIGHTNESS)
            if self.is_on:
                self.xpwm_rgbw_r.set_level(
                    scaleto100(self.xpwm_rgbw_r.level * self._brightness / 255),
                    self._transition,
                )
                self.xpwm_rgbw_g.set_level(
                    scaleto100(self.xpwm_rgbw_g.level * self._brightness / 255),
                    self._transition,
                )
                self.xpwm_rgbw_b.set_level(
                    scaleto100(self.xpwm_rgbw_b.level * self._brightness / 255),
                    self._transition,
                )
                self.xpwm_rgbw_w.set_level(
                    scaleto100(self.xpwm_rgbw_w.level * self._brightness / 255),
                    self._transition,
                )
            else:
                self.xpwm_rgbw_w.set_level(
                    scaleto100(self._brightness),
                    self._transition,
                )
        else:
            self.xpwm_rgbw_w.on(self._transition)

    def turn_off(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = int(kwargs.get(ATTR_TRANSITION) * 1000)
        self.xpwm_rgbw_r.off(self._transition)
        self.xpwm_rgbw_g.off(self._transition)
        self.xpwm_rgbw_b.off(self._transition)
        self.xpwm_rgbw_w.off(self._transition)
