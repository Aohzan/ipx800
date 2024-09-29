"""Generic IPX800V4 entity."""

from pypx800 import IPX800

from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_ICON,
    CONF_NAME,
    CONF_UNIT_OF_MEASUREMENT,
)
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
    CONF_TRANSITION,
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


class IpxEntity(CoordinatorEntity):
    """Representation of a IPX800 generic device entity."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
        suffix_name: str = "",
    ) -> None:
        """Initialize the device."""
        super().__init__(coordinator)

        self.ipx = ipx
        self._transition = int(
            device_config.get(CONF_TRANSITION, DEFAULT_TRANSITION) * 1000
        )
        self._ipx_type = device_config[CONF_TYPE]
        self._component = device_config[CONF_COMPONENT]
        self._id = device_config.get(CONF_ID)
        self._ext_id = device_config.get(CONF_EXT_ID)
        self._ids = device_config.get(CONF_IDS, [])

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
