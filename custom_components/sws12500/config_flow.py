"""Config flow for Sencor SWS 12500 Weather Station integration."""

import secrets
from typing import Any

import voluptuous as vol
from yarl import URL

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.network import get_url

from .const import (
    API_ID,
    API_KEY,
    DEV_DBG,
    DOMAIN,
    ECOWITT_ENABLED,
    ECOWITT_WEBHOOK_ID,
    INVALID_CREDENTIALS,
    POCASI_CZ_API_ID,
    POCASI_CZ_API_KEY,
    POCASI_CZ_ENABLED,
    POCASI_CZ_LOGGER_ENABLED,
    POCASI_CZ_SEND_INTERVAL,
    POCASI_CZ_SEND_MINIMUM,
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
        self.user_data: dict[str, Any] = {}
        self.user_data_schema = {}
        self.sensors: dict[str, Any] = {}
        self.migrate_schema = {}
        self.pocasi_cz: dict[str, Any] = {}
        self.pocasi_cz_schema = {}
        self.ecowitt: dict[str, Any] = {}
        self.ecowitt_schema = {}

        # @property
        # def config_entry(self) -> ConfigEntry:
        #     return self.hass.config_entries.async_get_entry(self.handler)

    async def _get_entry_data(self):
        """Get entry data."""

        self.user_data = {
            API_ID: self.config_entry.options.get(API_ID),
            API_KEY: self.config_entry.options.get(API_KEY),
            WSLINK: self.config_entry.options.get(WSLINK, False),
            DEV_DBG: self.config_entry.options.get(DEV_DBG, False),
        }

        self.user_data_schema = {
            vol.Required(API_ID, default=self.user_data.get(API_ID, "")): str,
            vol.Required(API_KEY, default=self.user_data.get(API_KEY, "")): str,
            vol.Optional(WSLINK, default=self.user_data.get(WSLINK, False)): bool,
            vol.Optional(DEV_DBG, default=self.user_data.get(DEV_DBG, False)): bool,
        }

        self.sensors = {
            SENSORS_TO_LOAD: (
                self.config_entry.options.get(SENSORS_TO_LOAD)
                if isinstance(self.config_entry.options.get(SENSORS_TO_LOAD), list)
                else []
            )
        }

        self.windy_data = {
            WINDY_API_KEY: self.config_entry.options.get(WINDY_API_KEY),
            WINDY_ENABLED: self.config_entry.options.get(WINDY_ENABLED, False),
            WINDY_LOGGER_ENABLED: self.config_entry.options.get(
                WINDY_LOGGER_ENABLED, False
            ),
        }

        self.windy_data_schema = {
            vol.Optional(
                WINDY_API_KEY, default=self.windy_data.get(WINDY_API_KEY, "")
            ): str,
            vol.Optional(WINDY_ENABLED, default=self.windy_data[WINDY_ENABLED]): bool
            or False,
            vol.Optional(
                WINDY_LOGGER_ENABLED,
                default=self.windy_data[WINDY_LOGGER_ENABLED],
            ): bool or False,
        }

        self.pocasi_cz = {
            POCASI_CZ_API_ID: self.config_entry.options.get(POCASI_CZ_API_ID, ""),
            POCASI_CZ_API_KEY: self.config_entry.options.get(POCASI_CZ_API_KEY, ""),
            POCASI_CZ_ENABLED: self.config_entry.options.get(POCASI_CZ_ENABLED, False),
            POCASI_CZ_LOGGER_ENABLED: self.config_entry.options.get(
                POCASI_CZ_LOGGER_ENABLED, False
            ),
            POCASI_CZ_SEND_INTERVAL: self.config_entry.options.get(
                POCASI_CZ_SEND_INTERVAL, 30
            ),
        }

        self.pocasi_cz_schema = {
            vol.Required(
                POCASI_CZ_API_ID, default=self.pocasi_cz.get(POCASI_CZ_API_ID)
            ): str,
            vol.Required(
                POCASI_CZ_API_KEY, default=self.pocasi_cz.get(POCASI_CZ_API_KEY)
            ): str,
            vol.Required(
                POCASI_CZ_SEND_INTERVAL,
                default=self.pocasi_cz.get(POCASI_CZ_SEND_INTERVAL),
            ): int,
            vol.Optional(
                POCASI_CZ_ENABLED, default=self.pocasi_cz.get(POCASI_CZ_ENABLED)
            ): bool,
            vol.Optional(
                POCASI_CZ_LOGGER_ENABLED,
                default=self.pocasi_cz.get(POCASI_CZ_LOGGER_ENABLED),
            ): bool,
        }

        self.ecowitt = {
            ECOWITT_WEBHOOK_ID: self.config_entry.options.get(ECOWITT_WEBHOOK_ID, ""),
            ECOWITT_ENABLED: self.config_entry.options.get(ECOWITT_ENABLED, False),
        }

    async def async_step_init(self, user_input: dict[str, Any] = {}):
        """Manage the options - show menu first."""
        return self.async_show_menu(
            step_id="init", menu_options=["basic", "ecowitt", "windy", "pocasi"]
        )

    async def async_step_basic(self, user_input: Any = None):
        """Manage basic options - credentials."""
        errors: dict[str, str] = {}

        await self._get_entry_data()

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
            user_input = self.retain_data(user_input)

            return self.async_create_entry(title=DOMAIN, data=user_input)

        self.user_data = user_input

        # we are ending with error msg, reshow form
        return self.async_show_form(
            step_id="basic",
            data_schema=vol.Schema(self.user_data_schema),
            errors=errors,
        )

    async def async_step_windy(self, user_input: Any = None):
        """Manage windy options."""
        errors: dict[str, str] = {}

        await self._get_entry_data()

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
                data_schema=vol.Schema(self.windy_data_schema),
                errors=errors,
            )

        user_input = self.retain_data(user_input)

        return self.async_create_entry(title=DOMAIN, data=user_input)

    async def async_step_pocasi(self, user_input: Any = None) -> ConfigFlowResult:
        """Handle the pocasi step."""

        errors: dict[str, str] = {}

        await self._get_entry_data()

        if user_input is None:
            return self.async_show_form(
                step_id="pocasi",
                data_schema=vol.Schema(self.pocasi_cz_schema),
                errors=errors,
            )

        if user_input.get(POCASI_CZ_SEND_INTERVAL, 0) < POCASI_CZ_SEND_MINIMUM:
            errors[POCASI_CZ_SEND_INTERVAL] = "pocasi_send_minimum"

        if user_input.get(POCASI_CZ_ENABLED):
            if user_input.get(POCASI_CZ_API_ID) == "":
                errors[POCASI_CZ_API_ID] = "pocasi_id_required"
            if user_input.get(POCASI_CZ_API_KEY) == "":
                errors[POCASI_CZ_API_KEY] = "pocasi_key_required"

        if len(errors) > 0:
            return self.async_show_form(
                step_id="pocasi",
                data_schema=vol.Schema(self.pocasi_cz_schema),
                errors=errors,
            )

        user_input = self.retain_data(user_input)

        return self.async_create_entry(title=DOMAIN, data=user_input)

    async def async_step_ecowitt(self, user_input: Any = None) -> ConfigFlowResult:
        """Ecowitt stations setup."""

        errors: dict[str, str] = {}
        await self._get_entry_data()

        if not (webhook := self.ecowitt.get(ECOWITT_WEBHOOK_ID)):
            webhook = secrets.token_hex(8)

        if user_input is None:
            url: URL = URL(get_url(self.hass))

            if not url.host:
                url.host = "UNKNOWN"

            ecowitt_schema = {
                vol.Required(
                    ECOWITT_WEBHOOK_ID,
                    default=webhook,
                ): str,
                vol.Optional(
                    ECOWITT_ENABLED,
                    default=self.ecowitt.get(ECOWITT_ENABLED, False),
                ): bool,
            }

            return self.async_show_form(
                step_id="ecowitt",
                data_schema=vol.Schema(ecowitt_schema),
                description_placeholders={
                    "url": url.host,
                    "port": str(url.port),
                    "webhook_id": webhook,
                },
                errors=errors,
            )

        user_input = self.retain_data(user_input)
        return self.async_create_entry(title=DOMAIN, data=user_input)

    def retain_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Retain user_data."""

        return {
            **self.user_data,
            **self.windy_data,
            **self.pocasi_cz,
            **self.sensors,
            **self.ecowitt,
            **dict(data),
        }


class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sencor SWS 12500 Weather Station."""

    data_schema = {
        vol.Required(API_ID): str,
        vol.Required(API_KEY): str,
        vol.Optional(WSLINK): bool,
        vol.Optional(DEV_DBG): bool,
    }

    VERSION = 1

    async def async_step_user(self, user_input: Any = None):
        """Handle the initial step."""
        if user_input is None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(self.data_schema),
            )

        errors: dict[str, str] = {}

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
    def async_get_options_flow(config_entry: ConfigEntry) -> ConfigOptionsFlowHandler:
        """Get the options flow for this handler."""
        return ConfigOptionsFlowHandler()
