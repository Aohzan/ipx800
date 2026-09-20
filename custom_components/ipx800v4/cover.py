"""Support for IPX800 V4 covers."""

from collections.abc import Awaitable, Callable
from typing import Any

from pypx800 import IPX800, X4VR, Ipx800CannotConnectError, Ipx800RequestError


from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .commands import error_details
from .coordinator import IpxDataUpdateCoordinator
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

PARALLEL_UPDATES = GLOBAL_PARALLEL_UPDATES


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
        coordinator: IpxDataUpdateCoordinator,
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
    def required_keys(self) -> tuple[str, ...]:
        """Raw response fields required by this entity."""
        return (f"VR{self._ext_id}-{self._id}",)

    @property
    def is_closed(self) -> bool:
        """Return the state."""
        return int(self.coordinator.data[f"VR{self._ext_id}-{self._id}"]) == 100

    @property
    def current_cover_position(self) -> int:
        """Return the current cover position."""
        return 100 - int(self.coordinator.data[f"VR{self._ext_id}-{self._id}"])

    async def _async_move(
        self,
        command: Callable[..., Awaitable[Any]],
        *args: Any,
        repeat: int = 20,
        retry: bool = True,
    ) -> None:
        """Start position reads after the first successful or ambiguous attempt."""
        tracking = False

        async def attempt():
            nonlocal tracking
            try:
                result = await command(*args)
            except (Ipx800CannotConnectError, Ipx800RequestError, TimeoutError) as err:
                if error_details(err)[1] and not tracking:
                    tracking = True
                    self.coordinator.async_track_cover_movement(repeat)
                raise
            else:
                if not tracking:
                    tracking = True
                    self.coordinator.async_track_cover_movement(repeat)
                return result

        await self._async_write(attempt, retry=retry)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open cover."""
        async with self._command_error("open cover", target=("position", 100)):
            await self._async_move(self.control.on)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        async with self._command_error("close cover", target=("position", 0)):
            await self._async_move(self.control.off)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        async with self._command_error("stop cover", target=("stop",)):
            await self._async_write(self.control.stop, retry=True)
        await self.coordinator.async_request_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the cover to a specific position."""
        async with self._command_error(
            "set cover position", target=("position", kwargs[ATTR_POSITION])
        ):
            await self._async_move(self.control.set_level, kwargs[ATTR_POSITION])

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        """Open the cover tilt."""
        async with self._command_error("open cover tilt"):
            await self._async_move(self.control.set_pulse_up, 1, repeat=3, retry=False)

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        """Close the cover tilt."""
        async with self._command_error("close cover tilt"):
            await self._async_move(
                self.control.set_pulse_down, 1, repeat=3, retry=False
            )
