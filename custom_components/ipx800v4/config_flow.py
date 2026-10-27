"""Config flow to configure the ipx800v4 integration."""

from typing import Any

import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import callback

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN


class IpxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a IPX800 config flow."""

    VERSION = 1

    async def async_step_import(self, import_info: dict[str, Any]) -> ConfigFlowResult:
        """Import a config entry from YAML config."""
        entry = await self.async_set_unique_id(
            f"{DOMAIN}, {import_info.get(CONF_NAME)}"
        )

        if entry:
            # The YAML configuration replaces the data, removed keys included
            if self.hass.config_entries.async_update_entry(
                entry, data=import_info
            ) and entry.state in (
                ConfigEntryState.LOADED,
                ConfigEntryState.SETUP_RETRY,
            ):
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
            return self.async_abort(reason="already_configured")

        return self.async_create_entry(title=import_info[CONF_NAME], data=import_info)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain the IPX800 is configured in configuration.yaml."""
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_abort(reason="yaml_only")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlowWithReload:
        """Define the config flow to handle options."""
        return Ipx800OptionsFlowHandler()


class Ipx800OptionsFlowHandler(OptionsFlowWithReload):
    """Handle a IPX800 options flow, the entry reloads with the new interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_SCAN_INTERVAL,
                        default=scan_interval,
                    ): probatio.All(probatio.Coerce(int), probatio.Range(min=1)),
                }
            ),
        )
