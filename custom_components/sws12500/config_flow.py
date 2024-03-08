"""Config flow for Sencor SWS 12500 Weather Station integration."""
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    API_ID,
    API_KEY,
    DOMAIN,
    INVALID_CREDENTIALS,
    WINDY_API_KEY,
    WINDY_ENABLED,
    WINDY_LOGGER_ENABLED,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(API_ID, default="API ID"): str,
        vol.Required(API_KEY, default="API KEY"): str,
    }
)


class CannotConnect(HomeAssistantError):
    """We can not connect. - not used in push mechanism."""


class InvalidAuth(HomeAssistantError):
    """Invalid auth exception."""


class ConfigOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle WeatherStation options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options - show menu first."""
        return self.async_show_menu(step_id="init", menu_options=["basic", "windy"])

    async def async_step_basic(self, user_input=None):
        """Manage basic options - credentials."""
        errors = {}

        api_id = self.config_entry.options.get(API_ID)
        api_key = self.config_entry.options.get(API_KEY)

        OPTIONAL_USER_DATA_SCHEMA = vol.Schema(  # pylint: disable=invalid-name
            {
                vol.Required(API_ID, default=api_id): str,
                vol.Required(API_KEY, default=api_key): str,
            }
        )

        if user_input is None:
            return self.async_show_form(
                step_id="basic", data_schema=OPTIONAL_USER_DATA_SCHEMA, errors=errors
            )

        if user_input[API_ID] in INVALID_CREDENTIALS:
            errors["base"] = "valid_credentials_api"
        elif user_input[API_KEY] in INVALID_CREDENTIALS:
            errors["base"] = "valid_credentials_key"
        elif user_input[API_KEY] == user_input[API_ID]:
            errors["base"] = "valid_credentials_match"
        else:
            # retain Windy options
            data: dict = {}
            data[WINDY_API_KEY] = self.config_entry.options.get(WINDY_API_KEY)
            data[WINDY_ENABLED] = self.config_entry.options.get(WINDY_ENABLED)
            data[WINDY_LOGGER_ENABLED] = self.config_entry.options.get(
                WINDY_LOGGER_ENABLED
            )

            data.update(user_input)

            return self.async_create_entry(title=DOMAIN, data=data)

        # we are ending with error msg, reshow form
        return self.async_show_form(
            step_id="basic", data_schema=OPTIONAL_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_windy(self, user_input=None):
        """Manage windy options."""
        errors = {}

        windy_key = self.config_entry.options.get(WINDY_API_KEY)
        windy_enabled = self.config_entry.options.get(WINDY_ENABLED)
        windy_logger_enabled = self.config_entry.options.get(WINDY_LOGGER_ENABLED)

        OPTIONAL_USER_DATA_SCHEMA = vol.Schema(  # pylint: disable=invalid-name
            {
                vol.Optional(WINDY_API_KEY, default=windy_key): str,
                vol.Optional(WINDY_ENABLED, default=windy_enabled): bool,
                vol.Optional(WINDY_LOGGER_ENABLED, default=windy_logger_enabled): bool,
            }
        )

        if user_input is None:
            return self.async_show_form(
                step_id="windy", data_schema=OPTIONAL_USER_DATA_SCHEMA, errors=errors
            )

        if (user_input[WINDY_ENABLED] is True) and (user_input[WINDY_API_KEY] == ""):
            errors["base"] = "windy_key_required"
            return self.async_show_form(
                step_id="windy", data_schema=OPTIONAL_USER_DATA_SCHEMA, errors=errors
            )

        # retain API_ID and API_KEY from config
        data: dict = {}
        data[API_ID] = self.config_entry.options.get(API_ID)
        data[API_KEY] = self.config_entry.options.get(API_KEY)

        data.update(user_input)

        return self.async_create_entry(title=DOMAIN, data=data)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sencor SWS 12500 Weather Station."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        if user_input[API_ID] in INVALID_CREDENTIALS:
            errors["base"] = "valid_credentials_api"
        elif user_input[API_KEY] in INVALID_CREDENTIALS:
            errors["base"] = "valid_credentials_key"
        elif user_input[API_KEY] == user_input[API_ID]:
            errors["base"] = "valid_credentials_match"
        else:
            return self.async_create_entry(
                title=DOMAIN, data=user_input, options=user_input
            )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ConfigOptionsFlowHandler:
        """Get the options flow for this handler."""
        return ConfigOptionsFlowHandler(config_entry)
