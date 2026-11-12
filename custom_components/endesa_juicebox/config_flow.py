"""Config flow for Endesa X JuiceBox."""
import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import JuiceBoxAPI
from .const import (
    CONF_AUTO_START_ON_PLUGIN,
    CONF_ENABLE_VICTRON_MQTT,
    CONF_VICTRON_TOPIC,
    DEFAULT_AUTO_START_ON_PLUGIN,
    DEFAULT_NAME,
    DEFAULT_PASSWORD,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VICTRON_TOPIC,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

class JuiceBoxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Endesa X JuiceBox."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            password = user_input[CONF_PASSWORD].strip()

            await self.async_set_unique_id(f"juicebox_{host}")
            self._abort_if_unique_id_configured()

            # Test connection
            session = async_get_clientsession(self.hass)
            api = JuiceBoxAPI(host=host, password=password, session=session)
            login_ok = await api.login()
            if not login_ok:
                errors["base"] = "cannot_connect"
            else:
                try:
                    await api.fetch_data()
                    return self.async_create_entry(
                        title=DEFAULT_NAME,
                        data=user_input,
                    )
                except Exception:
                    errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PASSWORD, default=DEFAULT_PASSWORD): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Optional(CONF_AUTO_START_ON_PLUGIN, default=DEFAULT_AUTO_START_ON_PLUGIN): bool,
                vol.Optional(CONF_ENABLE_VICTRON_MQTT, default=True): bool,
                vol.Optional(CONF_VICTRON_TOPIC, default=DEFAULT_VICTRON_TOPIC): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return JuiceBoxOptionsFlowHandler(config_entry)


class JuiceBoxOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options or self.config_entry.data
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Optional(
                    CONF_AUTO_START_ON_PLUGIN,
                    default=options.get(CONF_AUTO_START_ON_PLUGIN, DEFAULT_AUTO_START_ON_PLUGIN),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_VICTRON_MQTT,
                    default=options.get(CONF_ENABLE_VICTRON_MQTT, True),
                ): bool,
                vol.Optional(
                    CONF_VICTRON_TOPIC,
                    default=options.get(CONF_VICTRON_TOPIC, DEFAULT_VICTRON_TOPIC),
                ): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
