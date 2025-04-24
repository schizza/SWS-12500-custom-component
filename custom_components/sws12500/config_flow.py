"""Config flow for Sencor SWS 12500 Weather Station integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import UnitOfPrecipitationDepth, UnitOfVolumetricFlux
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.entity_registry as er

from .const import (
    API_ID,
    API_KEY,
    DEV_DBG,
    DOMAIN,
    INVALID_CREDENTIALS,
    MIG_FROM,
    MIG_TO,
    SENSOR_TO_MIGRATE,
    SENSORS_TO_LOAD,
    WINDY_API_KEY,
    WINDY_ENABLED,
    WINDY_LOGGER_ENABLED,
    WSLINK,
)
from .utils import long_term_units_in_statistics_meta, migrate_data

_LOGGER = logging.getLogger(__name__)


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
        self.migrate_sensor_select = {}
        self.migrate_unit_selection = {}
        self.count = 0
        self.selected_sensor = ""

        self.unit_values = [unit.value for unit in UnitOfVolumetricFlux]
        self.unit_values.extend([unit.value for unit in UnitOfPrecipitationDepth])

        @property
        def config_entry(self):
            return self.hass.config_entries.async_get_entry(self.handler)

    async def _get_entry_data(self):
        """Get entry data."""

        self.user_data: dict[str, Any] = {
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

        self.sensors: dict[str, Any] = {
            SENSORS_TO_LOAD: self.config_entry.options.get(SENSORS_TO_LOAD)
            if isinstance(self.config_entry.options.get(SENSORS_TO_LOAD), list)
            else []
        }

        self.windy_data: dict[str, Any] = {
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

        self.migrate_sensor_select = {
            vol.Required(SENSOR_TO_MIGRATE): vol.In(
                await self.load_sensors_to_migrate() or {}
            ),
        }

        self.migrate_unit_selection = {
            vol.Required(MIG_FROM): vol.In(self.unit_values),
            vol.Required(MIG_TO): vol.In(self.unit_values),
            vol.Optional("trigger_action", default=False): bool,
        }
        # "mm/d", "mm/h", "mm", "in/d", "in/h", "in"

    async def load_sensors_to_migrate(self) -> dict[str, Any]:
        """Load sensors to migrate."""

        sensor_statistics = await long_term_units_in_statistics_meta(self.hass)

        entity_registry = er.async_get(self.hass)
        sensors = entity_registry.entities.get_entries_for_config_entry_id(
            self.config_entry.entry_id
        )

        return {
            sensor.entity_id: f"{sensor.name or sensor.original_name} (current settings: {sensor.unit_of_measurement}, longterm stats unit: {sensor_statistics.get(sensor.entity_id)})"
            for sensor in sensors
            if sensor.unique_id in {"rain", "daily_rain"}
        }

    async def async_step_init(self, user_input=None):
        """Manage the options - show menu first."""
        return self.async_show_menu(
            step_id="init", menu_options=["basic", "windy", "migration"]
        )

    async def async_step_basic(self, user_input=None):
        """Manage basic options - credentials."""
        errors = {}

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

        # retain user_data
        user_input.update(self.user_data)

        # retain senors
        user_input.update(self.sensors)

        return self.async_create_entry(title=DOMAIN, data=user_input)

    async def async_step_migration(self, user_input=None):
        """Migrate sensors."""

        errors = {}

        data_schema = vol.Schema(self.migrate_sensor_select)
        data_schema.schema.update()

        await self._get_entry_data()

        if user_input is None:
            return self.async_show_form(
                step_id="migration",
                data_schema=vol.Schema(self.migrate_sensor_select),
                errors=errors,
                description_placeholders={
                    "migration_status": "-",
                    "migration_count": "-",
                },
            )

        self.selected_sensor = user_input.get(SENSOR_TO_MIGRATE)

        return await self.async_step_migration_units()

    async def async_step_migration_units(self, user_input=None):
        """Migrate unit step."""

        registry = er.async_get(self.hass)
        sensor_entry = registry.async_get(self.selected_sensor)
        sensor_stats = await long_term_units_in_statistics_meta(self.hass)

        default_unit = sensor_entry.unit_of_measurement if sensor_entry else None

        if default_unit not in self.unit_values:
            default_unit = self.unit_values[0]

        data_schema = vol.Schema({
            vol.Required(MIG_FROM, default=default_unit): vol.In(self.unit_values),
            vol.Required(MIG_TO): vol.In(self.unit_values),
            vol.Optional("trigger_action", default=False): bool,
        })

        if user_input is None:
            return self.async_show_form(
                step_id="migration_units",
                data_schema=data_schema,
                errors={},
                description_placeholders={
                    "migration_sensor": sensor_entry.original_name,
                    "migration_stats": sensor_stats.get(self.selected_sensor),
                },
            )

        if user_input.get("trigger_action"):
            self.count = await migrate_data(
                self.hass,
                self.selected_sensor,
                user_input.get(MIG_FROM),
                user_input.get(MIG_TO),
            )

            registry.async_update_entity(self.selected_sensor,
                unit_of_measurement=user_input.get(MIG_TO),
            )

            state = self.hass.states.get(self.selected_sensor)
            if state:
                _LOGGER.info("State attributes before update: %s", state.attributes)
                attributes = dict(state.attributes)
                attributes["unit_of_measurement"] = user_input.get(MIG_TO)
                self.hass.states.async_set(self.selected_sensor, state.state, attributes)
                _LOGGER.info("State attributes after update: %s", attributes)

                options = {**self.config_entry.options, "reload_sensor": self.selected_sensor}
                self.hass.config_entries.async_update_entry(self.config_entry, options=options)

            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            await self.hass.async_block_till_done()

            _LOGGER.info("Migration complete for sensor %s: %s row updated, new measurement unit: %s, ",
                         self.selected_sensor,
                         self.count,
                         user_input.get(MIG_TO),
                        )

            await self._get_entry_data()
            sensor_entry = er.async_get(self.hass).async_get(self.selected_sensor)
            sensor_stat = await self.load_sensors_to_migrate()

            return self.async_show_form(
                step_id="migration_complete",
                data_schema=vol.Schema({}),
                errors={},
                description_placeholders={
                    "migration_sensor": sensor_entry.unit_of_measurement,
                    "migration_stats": sensor_stat.get(self.selected_sensor),
                    "migration_count": self.count,
                },
            )

        # retain windy data
        user_input.update(self.windy_data)

        # retain user_data
        user_input.update(self.user_data)

        # retain senors
        user_input.update(self.sensors)

        return self.async_create_entry(title=DOMAIN, data=user_input)

    async def async_step_migration_complete(self, user_input=None):
        """Migration complete."""

        errors = {}

        await self._get_entry_data()
        sensor_entry = er.async_get(self.hass).async_get(self.selected_sensor)
        sensor_stat = await self.load_sensors_to_migrate()

        if user_input is None:
            return self.async_show_form(
                step_id="migration_complete",
                data_schema=vol.Schema({}),
                errors=errors,
                description_placeholders={
                    "migration_sensor": sensor_entry.unit_of_measurement,
                    "migration_stats": sensor_stat.get(self.selected_sensor),
                    "migration_count": self.count,
                },
            )

        # retain windy data
        user_input.update(self.windy_data)

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
