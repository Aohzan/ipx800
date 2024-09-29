"""Config flow to configure the ipx800v4 integration."""

from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import (
    CONN_CLASS_LOCAL_POLL,
    HANDLERS,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import callback

from .const import COORDINATOR, DEFAULT_SCAN_INTERVAL, DOMAIN


@HANDLERS.register(DOMAIN)
class IpxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a IPX800 config flow."""

    VERSION = 1
    CONNECTION_CLASS = CONN_CLASS_LOCAL_POLL

    async def async_step_import(self, import_info) -> ConfigFlowResult:
        """Import a config entry from YAML config."""
        entry = await self.async_set_unique_id(
            f"{DOMAIN}, {import_info.get(CONF_NAME)}"
        )

        if entry:
            self.hass.config_entries.async_update_entry(entry, data=import_info)
            self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=import_info.get(CONF_NAME), data=import_info
        )

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Get configuration from the user."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
                errors={},
            )
        return self.async_abort(reason="yaml_only")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Define the config flow to handle options."""
        return Ipx800OptionsFlowHandler(config_entry)


class Ipx800OptionsFlowHandler(OptionsFlow):
    """Handle a IPX800 options flow."""

    def __init__(self, config_entry) -> None:
        """Initialize."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id][
                COORDINATOR
            ]
            update_interval_sec = user_input[CONF_SCAN_INTERVAL]
            update_interval = timedelta(seconds=update_interval_sec)
            coordinator.update_interval = update_interval
            return self.async_create_entry(title="", data=user_input)

        scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=scan_interval,
                    ): int,
                }
            ),
        )
