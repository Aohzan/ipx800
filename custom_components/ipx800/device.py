import logging
import re
from .const import *
from homeassistant.const import (
    CONF_NAME,
    CONF_ICON,
    CONF_DEVICE_CLASS,
    CONF_UNIT_OF_MEASUREMENT,
)
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)


class IpxDevice(Entity):
    """Representation of a IPX800 generic device entity."""

    def __init__(self, ipx_device, suffix_name=""):
        """Initialize the device."""
        self.config = ipx_device.get("config")
        self.controller = ipx_device.get("controller")
        self.coordinator = self.controller.coordinator

        self._name = self.config.get(CONF_NAME)
        if suffix_name:
            self._name += f" {suffix_name}"
        self._device_class = self.config.get(CONF_DEVICE_CLASS) or None
        self._unit_of_measurement = self.config.get(CONF_UNIT_OF_MEASUREMENT) or None
        self._transition = int(self.config.get(CONF_TRANSITION, DEFAULT_TRANSITION) * 1000)
        self._icon = self.config.get(CONF_ICON) or None
        self._state = None
        self._id = self.config.get(CONF_ID)
        self._ext_id = self.config.get(CONF_EXT_ID) or None
        self._ids = self.config.get(CONF_IDS) or []

        self._supported_features = 0
        self._unique_id = (
            f"{self.controller.name}.{self.config.get(CONF_COMPONENT)}.{re.sub('[^A-Za-z0-9_]+', '', self._name.replace(' ', '_'))}"
        ).lower()

    @property
    def should_poll(self):
        """No polling since coordinator used"""
        return False

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
            "name": self._name,
            "manufacturer": "GCE",
            "model": "IPX800v4",
            "via_device": (DOMAIN, self.controller.name),
        }

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._unique_id

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_features

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update the entity."""
        await self.coordinator.async_request_refresh()
