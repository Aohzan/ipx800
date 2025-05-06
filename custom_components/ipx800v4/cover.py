"""Support for IPX800 V4 covers."""

import logging
from typing import Any
import asyncio

from pypx800 import IPX800, X4VR, Ipx800RequestError

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
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
    TYPE_X4VR_BSO,
)
from .entity import IpxEntity

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES

current_task_refresh_state = None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IPX800 covers."""
    controller = hass.data[DOMAIN][entry.entry_id][CONTROLLER]
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    devices = hass.data[DOMAIN][entry.entry_id][CONF_DEVICES]["cover"]

    entities: list[CoverEntity] = []

    for device in devices:
        entities.append(X4VRCover(device, controller, coordinator))  # noqa: PERF401

    async_add_entities(entities, True)


class X4VRCover(IpxEntity, CoverEntity):
    """Representation of a IPX Cover through X4VR."""

    def __init__(
        self,
        device_config: dict,
        ipx: IPX800,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the X4VRCover."""
        super().__init__(device_config, ipx, coordinator)
        self.control = X4VR(ipx, self._ext_id, self._id)
        self._attr_device_class = CoverDeviceClass.SHUTTER
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )
        if device_config[CONF_TYPE] == TYPE_X4VR_BSO:
            self._attr_supported_features |= (
                CoverEntityFeature.CLOSE_TILT | CoverEntityFeature.OPEN_TILT
            )

    @property
    def is_closed(self) -> bool:
        """Return the state."""
        return int(self.coordinator.data[f"VR{self._ext_id}-{self._id}"]) == 100

    @property
    def current_cover_position(self) -> int:
        """Return the current cover position."""
        return 100 - int(self.coordinator.data[f"VR{self._ext_id}-{self._id}"])

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open cover."""
        try:
            await self.control.on()
            await self.async_launch_refresh_state(20)
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while open IPX800 cover: %s", self.name)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        try:
            await self.control.off()
            await self.async_launch_refresh_state(20)
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while close IPX800 cover: %s", self.name)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        try:
            await self.control.stop()
            await self.coordinator.async_request_refresh()
        except Ipx800RequestError:
            _LOGGER.error("An error occurred while stop IPX800 cover: %s", self.name)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the cover to a specific position."""
        try:
            await self.control.set_level(kwargs[ATTR_POSITION])
            await self.async_launch_refresh_state(20)
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while set IPX800 cover position: %s", self.name
            )

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        """Open the cover tilt."""
        try:
            await self.control.set_pulse_up(1)
            await self.async_launch_refresh_state(3)
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while set IPX800 tilt position: %s", self.name
            )

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        """Close the cover tilt."""
        try:
            await self.control.set_pulse_down(1)
            await self.async_launch_refresh_state(3)
        except Ipx800RequestError:
            _LOGGER.error(
                "An error occurred while set IPX800 cover position: %s", self.name
            )

    async def async_launch_refresh_state(self,repeat:int = 20) -> None:
        global current_task_refresh_state
        if current_task_refresh_state and not current_task_refresh_state.done():
            current_task_refresh_state.cancel()
        current_task_refresh_state = asyncio.create_task(self.async_refresh_cover_state(repeat))

    async def async_refresh_cover_state(self,repeat:int = 20) -> None:
        if repeat > 20:
            repeat = 20
        if repeat < 1:
            repeat = 1
        for i in range(repeat):
            try:
                await self.coordinator.async_request_refresh()
            except Exception as e:
                _LOGGER.error(
                    "An error occurred while refreshing the cover state: %s", str(e)
                )
            await asyncio.sleep(2)
