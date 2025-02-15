"""Config flow for Sencor SWS 12500 Weather Station integration."""

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    API_ID,
    API_KEY,
    DEV_DBG,
    DOMAIN,
    INVALID_CREDENTIALS,
    SENSORS_TO_LOAD,
    WINDY_API_KEY,
    WINDY_ENABLED,
    WINDY_LOGGER_ENABLED,
    WSLINK,
)


class CannotConnect(HomeAssistantError):
    """We can not connect. - not used in push mechanism."""


class InvalidAuth(HomeAssistantError):
    """Invalid auth exception."""


class ConfigOptionsFlowHandler(OptionsFlow):
    """Handle WeatherStation ConfigFlow."""

    def __init__(self) -> None:
        """Initialize flow."""
        super().__init__()

        self.windy_data: dict[str, Any] = {}
        self.windy_data_schema = {}
        self.user_data: dict[str, str] = {}
        self.user_data_schema = {}
        self.sensors: dict[str, Any] = {}

        @property
        def config_entry(self):
            return self.hass.config_entries.async_get_entry(self.handler)

    def _get_entry_data(self):
        """Get entry data."""

        self.user_data: dict[str, Any] = {
            API_ID: self.config_entry.options.get(API_ID),
            API_KEY: self.config_entry.options.get(API_KEY),
            WSLINK: self.config_entry.options.get(WSLINK),
            DEV_DBG: self.config_entry.options.get(DEV_DBG),
        }

        self.user_data_schema = {
            vol.Required(API_ID, default=self.user_data[API_ID] or ""): str,
            vol.Required(API_KEY, default=self.user_data[API_KEY] or ""): str,
            vol.Optional(WSLINK, default=self.user_data[WSLINK]): bool,
            vol.Optional(DEV_DBG, default=self.user_data[DEV_DBG]): bool,
        }

        self.sensors: dict[str, Any] = {
            SENSORS_TO_LOAD: self.config_entry.options.get(SENSORS_TO_LOAD)
            if isinstance(self.config_entry.options.get(SENSORS_TO_LOAD), list)
            else []
        }

        self.windy_data: dict[str, Any] = {
            WINDY_API_KEY: self.config_entry.options.get(WINDY_API_KEY),
            WINDY_ENABLED: self.config_entry.options.get(WINDY_ENABLED)
            if isinstance(self.config_entry.options.get(WINDY_ENABLED), bool)
            else False,
            WINDY_LOGGER_ENABLED: self.config_entry.options.get(WINDY_LOGGER_ENABLED)
            if isinstance(self.config_entry.options.get(WINDY_LOGGER_ENABLED), bool)
            else False,
        }

        self.windy_data_schema = {
            vol.Optional(
                WINDY_API_KEY, default=self.windy_data[WINDY_API_KEY] or ""
            ): str,
            vol.Optional(WINDY_ENABLED, default=self.windy_data[WINDY_ENABLED]): bool,
            vol.Optional(
                WINDY_LOGGER_ENABLED,
                default=self.windy_data[WINDY_LOGGER_ENABLED],
            ): bool,
        }

    async def async_step_init(self, user_input=None):
        """Manage the options - show menu first."""
        return self.async_show_menu(step_id="init", menu_options=["basic", "windy"])

    async def async_step_basic(self, user_input=None):
        """Manage basic options - credentials."""
        errors = {}

        self._get_entry_data()

        if user_input is None:
            return self.async_show_form(
                step_id="basic",
                data_schema=vol.Schema(self.user_data_schema),
                errors=errors,
            )

        if user_input[API_ID] in INVALID_CREDENTIALS:
            errors[API_ID] = "valid_credentials_api"
        elif user_input[API_KEY] in INVALID_CREDENTIALS:
            errors[API_KEY] = "valid_credentials_key"
        elif user_input[API_KEY] == user_input[API_ID]:
            errors["base"] = "valid_credentials_match"
        else:
            # retain windy data
            user_input.update(self.windy_data)

            # retain sensors
            user_input.update(self.sensors)

            return self.async_create_entry(title=DOMAIN, data=user_input)

        self.user_data = user_input

        # we are ending with error msg, reshow form
        return self.async_show_form(
            step_id="basic",
            data_schema=vol.Schema(self.user_data_schema),
            errors=errors,
        )

    async def async_step_windy(self, user_input=None):
        """Manage windy options."""
        errors = {}

        self._get_entry_data()

        if user_input is None:
            return self.async_show_form(
                step_id="windy",
                data_schema=vol.Schema(self.windy_data_schema),
                errors=errors,
            )

        if (user_input[WINDY_ENABLED] is True) and (user_input[WINDY_API_KEY] == ""):
            errors[WINDY_API_KEY] = "windy_key_required"
            return self.async_show_form(
                step_id="windy",
                data_schema=self.windy_data_schema,
                description_placeholders={
                    WINDY_ENABLED: True,
                    WINDY_LOGGER_ENABLED: user_input[WINDY_LOGGER_ENABLED],
                },
                errors=errors,
            )

        # retain user_data
        user_input.update(self.user_data)

        # retain senors
        user_input.update(self.sensors)

        return self.async_create_entry(title=DOMAIN, data=user_input)


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sencor SWS 12500 Weather Station."""

    data_schema = {
        vol.Required(API_ID): str,
        vol.Required(API_KEY): str,
        vol.Optional(WSLINK): bool,
        vol.Optional(DEV_DBG): bool,
    }

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(self.data_schema),
            )

        errors = {}

        if user_input[API_ID] in INVALID_CREDENTIALS:
            errors[API_ID] = "valid_credentials_api"
        elif user_input[API_KEY] in INVALID_CREDENTIALS:
            errors[API_KEY] = "valid_credentials_key"
        elif user_input[API_KEY] == user_input[API_ID]:
            errors["base"] = "valid_credentials_match"
        else:
            return self.async_create_entry(
                title=DOMAIN, data=user_input, options=user_input
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(self.data_schema),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> ConfigOptionsFlowHandler:
        """Get the options flow for this handler."""
        return ConfigOptionsFlowHandler()
