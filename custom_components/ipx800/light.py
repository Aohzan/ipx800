"""Support for IPX800 lights."""
import logging

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.components.light import (
    DOMAIN,
    LightEntity,
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    ATTR_WHITE_VALUE,
    ATTR_RGB_COLOR,
    ATTR_HS_COLOR,
    SUPPORT_BRIGHTNESS,
    SUPPORT_TRANSITION,
    SUPPORT_COLOR,
    SUPPORT_WHITE_VALUE,
)
import homeassistant.util.color as color_util

from . import IPX800_DEVICES, IpxDevice, DEFAULT_TRANSITION

_LOGGER = logging.getLogger(__name__)


def scaleto255(value):
    return max(0, min(255, round((value * 255.0) / 100.0)))


def scaleto100(value):
    return max(0, min(100, round((value * 100.0) / 255.0)))


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the IPX800 lights."""
    add_entities(
        [
            RelayLight(device)
            for device in (
                item
                for item in hass.data[IPX800_DEVICES]["light"]
                if item.get("config").get("relay")
            )
        ],
        True,
    )

    add_entities(
        [
            XDimmerLight(device)
            for device in (
                item
                for item in hass.data[IPX800_DEVICES]["light"]
                if item.get("config").get("xdimmer")
            )
        ],
        True,
    )

    add_entities(
        [
            XPWMLight(device)
            for device in (
                item
                for item in hass.data[IPX800_DEVICES]["light"]
                if item.get("config").get("xpwm")
            )
        ],
        True,
    )

    add_entities(
        [
            XPWMRGBLight(device)
            for device in (
                item
                for item in hass.data[IPX800_DEVICES]["light"]
                if item.get("config").get("xpwm_rgb")
            )
        ],
        True,
    )

    add_entities(
        [
            XPWMRGBWLight(device)
            for device in (
                item
                for item in hass.data[IPX800_DEVICES]["light"]
                if item.get("config").get("xpwm_rgbw")
            )
        ],
        True,
    )


class RelayLight(IpxDevice, LightEntity):
    """Representation of a IPX Light through relay."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.relay = self.controller.ipx.relays[self.config.get("relay")]

    @property
    def is_on(self) -> bool:
        """Return true if the IPX800 device is on."""
        return self._state

    def turn_on(self):
        """Turn on the IPX800 device."""
        self.relay.on()
        self._state = True

    def turn_off(self):
        """Turn off the IPX800 device."""
        self.relay.off()
        self._state = False

    def toggle(self):
        """Toggle the IPX800 device."""
        self.relay.toggle()

    def update(self):
        """Update the IPX800 device status."""
        try:
            self._state = self.relay.status
        except KeyError:
            _LOGGER.warning("Update of %s failed.", self._name)
            raise ConfigEntryNotReady


class XDimmerLight(IpxDevice, LightEntity):
    """Representation of a IPX Light through X-DIMMER."""

    def __init__(self, ipx_device):
        super().__init__(ipx_device)
        self.xdimmer = self.controller.ipx.xdimmers[self.config.get("xdimmer")]

        self._brightness = None
        self._supported_flags |= SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION

    @property
    def is_on(self) -> bool:
        return self._state

    @property
    def brightness(self):
        return self._brightness

    def turn_on(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = kwargs.get(ATTR_TRANSITION, DEFAULT_TRANSITION) * 1000
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
            self.xdimmer.set_level(scaleto100(self._brightness), self._transition)
        else:
            self.xdimmer.on(self._transition)
        self._state = True

    def turn_off(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = kwargs.get(ATTR_TRANSITION, DEFAULT_TRANSITION) * 1000
        self.xdimmer.off(self._transition)
        self._state = False

    def toggle(self):
        self.xdimmer.toggle()

    def update(self):
        try:
            self._state = self.xdimmer.status
            self._brightness = scaleto255(self.xdimmer.level)
        except KeyError:
            _LOGGER.warning("Update of %s failed.", self._name)
            raise ConfigEntryNotReady


class XPWMLight(IpxDevice, LightEntity):
    """Representation of a IPX Light through X-PWM single channel."""

    def __init__(self, ipx_device):
        super().__init__(ipx_device)
        self.xpwm = self.controller.ipx.xpwm[self.config.get("xpwm")]

        self._brightness = None
        self._supported_flags |= SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION

    @property
    def is_on(self) -> bool:
        return self._state

    @property
    def brightness(self):
        return self._brightness

    def turn_on(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = kwargs.get(ATTR_TRANSITION, DEFAULT_TRANSITION) * 1000
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
            self.xpwm.set_level(scaleto100(self._brightness), self._transition)
        else:
            self.xpwm.on(self._transition)
        self._state = True

    def turn_off(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = kwargs.get(ATTR_TRANSITION, DEFAULT_TRANSITION) * 1000
        self.xpwm.off(self._transition)
        self._state = False

    def toggle(self):
        self.xpwm.toggle()

    def update(self):
        try:
            self._state = self.xpwm.status
            self._brightness = scaleto255(self.xpwm.level)
        except KeyError:
            _LOGGER.warning("Update of %s failed.", self._name)
            raise ConfigEntryNotReady


class XPWMRGBLight(IpxDevice, LightEntity):
    """Representation of a RGB Light through 3 X-PWM channel."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.xpwm_rgb_r = self.controller.ipx.xpwm[self.config.get("xpwm_rgb")[0]]
        self.xpwm_rgb_g = self.controller.ipx.xpwm[self.config.get("xpwm_rgb")[1]]
        self.xpwm_rgb_b = self.controller.ipx.xpwm[self.config.get("xpwm_rgb")[2]]

        self._brightness = None
        self._hs_color = None
        self._rgb_color = None
        self._supported_flags |= SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION | SUPPORT_COLOR

    @property
    def is_on(self) -> bool:
        return self._state

    @property
    def brightness(self):
        return self._brightness

    @property
    def rgb_color(self):
        return self._rgb_color

    @property
    def hs_color(self):
        return self._hs_color

    def turn_on(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = kwargs.get(ATTR_TRANSITION, DEFAULT_TRANSITION) * 1000

        if ATTR_RGB_COLOR in kwargs or ATTR_HS_COLOR in kwargs:
            if ATTR_RGB_COLOR in kwargs:
                self._rgb_color = kwargs.get(ATTR_RGB_COLOR)
            elif ATTR_HS_COLOR in kwargs:
                self._rgb_color = color_util.color_hs_to_RGB(*kwargs.get(ATTR_HS_COLOR))
            self.xpwm_rgb_r.set_level(scaleto100(self._rgb_color[0]), self._transition)
            self.xpwm_rgb_g.set_level(scaleto100(self._rgb_color[1]), self._transition)
            self.xpwm_rgb_b.set_level(scaleto100(self._rgb_color[2]), self._transition)
        elif ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs.get(ATTR_BRIGHTNESS)
            if self._state:
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
                    scaleto100(self._brightness), self._transition
                )
                self.xpwm_rgb_g.set_level(
                    scaleto100(self._brightness), self._transition
                )
                self.xpwm_rgb_b.set_level(
                    scaleto100(self._brightness), self._transition
                )
        else:
            self.xpwm_rgb_r.on(self._transition)
            self.xpwm_rgb_g.on(self._transition)
            self.xpwm_rgb_b.on(self._transition)

        self._state = True

    def turn_off(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = kwargs.get(ATTR_TRANSITION, DEFAULT_TRANSITION) * 1000
        self.xpwm_rgb_r.off(self._transition)
        self.xpwm_rgb_g.off(self._transition)
        self.xpwm_rgb_b.off(self._transition)
        self._state = False

    def toggle(self):
        self.xpwm_rgb_r.toggle(self._transition)
        self.xpwm_rgb_g.toggle(self._transition)
        self.xpwm_rgb_b.toggle(self._transition)

    def update(self):
        try:
            # one query to get all levels
            levels = self.xpwm_rgb_r.level_all_channels
            level_r = scaleto255(levels[f"PWM{self.config.get('xpwm_rgb')[0]}"])
            level_g = scaleto255(levels[f"PWM{self.config.get('xpwm_rgb')[1]}"])
            level_b = scaleto255(levels[f"PWM{self.config.get('xpwm_rgb')[2]}"])
            self._state = level_r > 0 or level_b > 0 or level_g > 0
            self._rgb_color = [level_r, level_g, level_b]
            self._brightness = 0.2126 * level_r + 0.7152 * level_g + 0.0722 * level_b
        except KeyError:
            _LOGGER.warning("Update of %s failed.", self._name)
            raise ConfigEntryNotReady


class XPWMRGBWLight(IpxDevice, LightEntity):
    """Representation of a IPX Light through X-PWM single channel."""

    def __init__(self, ipx_device):
        """Initialize the IPX device."""
        super().__init__(ipx_device)
        self.xpwm_rgbw_r = self.controller.ipx.xpwm[self.config.get("xpwm_rgbw")[0]]
        self.xpwm_rgbw_g = self.controller.ipx.xpwm[self.config.get("xpwm_rgbw")[1]]
        self.xpwm_rgbw_b = self.controller.ipx.xpwm[self.config.get("xpwm_rgbw")[2]]
        self.xpwm_rgbw_w = self.controller.ipx.xpwm[self.config.get("xpwm_rgbw")[3]]

        self._brightness = None
        self._hs_color = None
        self._rgb_color = None
        self._white_value = None
        self._supported_flags |= (
            SUPPORT_BRIGHTNESS
            | SUPPORT_TRANSITION
            | SUPPORT_COLOR
            | SUPPORT_WHITE_VALUE
        )

    @property
    def is_on(self) -> bool:
        return self._state

    @property
    def brightness(self):
        return self._brightness

    @property
    def rgb_color(self):
        return self._rgb_color

    @property
    def hs_color(self):
        return self._hs_color

    @property
    def white_value(self):
        return self._white_value

    def turn_on(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = kwargs.get(ATTR_TRANSITION, DEFAULT_TRANSITION) * 1000

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
            if self._state:
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
                    scaleto100(self._brightness), self._transition
                )
        else:
            self.xpwm_rgbw_w.on(self._transition)

        self._state = True

    def turn_off(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            self._transition = kwargs.get(ATTR_TRANSITION, DEFAULT_TRANSITION) * 1000
        self.xpwm_rgbw_r.off(self._transition)
        self.xpwm_rgbw_g.off(self._transition)
        self.xpwm_rgbw_b.off(self._transition)
        self.xpwm_rgbw_w.off(self._transition)
        self._state = False

    def toggle(self):
        self.xpwm_rgbw_w.toggle()

    def update(self):
        try:
            # one query to get all levels
            levels = self.xpwm_rgbw_w.level_all_channels
            level_r = scaleto255(levels[f"PWM{self.config.get('xpwm_rgbw')[0]}"])
            level_g = scaleto255(levels[f"PWM{self.config.get('xpwm_rgbw')[1]}"])
            level_b = scaleto255(levels[f"PWM{self.config.get('xpwm_rgbw')[2]}"])
            level_w = scaleto255(levels[f"PWM{self.config.get('xpwm_rgbw')[3]}"])
            self._state = level_r > 0 or level_b > 0 or level_g > 0 or level_w > 0
            self._white_value = level_w
            self._rgb_color = [level_r, level_g, level_b]
            # if any or RGB is on, brightness is them level, otherwise, brightness is white value
            if level_r > 0 or level_b > 0 or level_g > 0:
                self._brightness = (
                    0.2126 * level_r + 0.7152 * level_g + 0.0722 * level_b
                )
            else:
                self._brightness = level_w
        except KeyError:
            _LOGGER.warning("Update of %s failed.", self._name)
            raise ConfigEntryNotReady
