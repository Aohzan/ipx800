"""Config flow to configure the ipx800v4 integration."""
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME

from .const import DOMAIN


@config_entries.HANDLERS.register(DOMAIN)
class IpxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a IPX800 config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_import(self, import_info):
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

    async def async_step_user(self, user_input=None):
        """Get configuration from the user."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
                errors={},
            )
        return self.async_abort(reason="yaml_only")
