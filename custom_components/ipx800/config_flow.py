"""Config flow to configure the ipx800 integration."""
import logging

from homeassistant import config_entries
from homeassistant import data_entry_flow

from .const import DOMAIN
from homeassistant.const import CONF_NAME

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class IpxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_import(self, user_input):
        """Import a config entry."""
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(f"{DOMAIN}, {user_input.get(CONF_NAME)}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input.get(CONF_NAME), data=user_input
            )
