"""Diagnostics support for the GCE IPX800 V4 integration."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_PUSH_PASSWORD
from .coordinator import IpxConfigEntry

TO_REDACT = {CONF_API_KEY, CONF_PASSWORD, CONF_PUSH_PASSWORD, CONF_USERNAME, "mac"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: IpxConfigEntry
) -> dict[str, Any]:
    """Return the diagnostics of a config entry."""
    data = entry.runtime_data
    coordinator = data.coordinator
    return {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "devices": data.devices,
        "push_enabled": data.push_config is not None,
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_successful_read": coordinator.last_successful_read,
            "consecutive_failures": coordinator.consecutive_failures,
            "data": coordinator.data,
        },
        "system": async_redact_data(data.system_coordinator.data or {}, TO_REDACT),
    }
