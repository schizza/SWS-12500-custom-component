from __future__ import annotations

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sws12500.const import (
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
    WINDY_ENABLED,
    WINDY_LOGGER_ENABLED,
    WINDY_STATION_ID,
    WINDY_STATION_PW,
    WSLINK,
)
from homeassistant import config_entries


@pytest.mark.asyncio
async def test_config_flow_user_form_then_create_entry(
    hass, enable_custom_integrations
) -> None:
    """Online HA: config flow shows form then creates entry and options."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    user_input = {
        API_ID: "my_id",
        API_KEY: "my_key",
        WSLINK: False,
        DEV_DBG: False,
    }
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=user_input
    )
    assert result2["type"] == "create_entry"
    assert result2["title"] == DOMAIN
    assert result2["data"] == user_input
    assert result2["options"] == user_input


@pytest.mark.asyncio
async def test_config_flow_user_invalid_credentials_api_id(
    hass, enable_custom_integrations
) -> None:
    """API_ID in INVALID_CREDENTIALS -> error on API_ID."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"

    user_input = {
        API_ID: INVALID_CREDENTIALS[0],
        API_KEY: "ok_key",
        WSLINK: False,
        DEV_DBG: False,
    }
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=user_input
    )
    assert result2["type"] == "form"
    assert result2["step_id"] == "user"
    assert result2["errors"][API_ID] == "valid_credentials_api"


@pytest.mark.asyncio
async def test_config_flow_user_invalid_credentials_api_key(
    hass, enable_custom_integrations
) -> None:
    """API_KEY in INVALID_CREDENTIALS -> error on API_KEY."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"

    user_input = {
        API_ID: "ok_id",
        API_KEY: INVALID_CREDENTIALS[0],
        WSLINK: False,
        DEV_DBG: False,
    }
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=user_input
    )
    assert result2["type"] == "form"
    assert result2["step_id"] == "user"
    assert result2["errors"][API_KEY] == "valid_credentials_key"


@pytest.mark.asyncio
async def test_config_flow_user_invalid_credentials_match(
    hass, enable_custom_integrations
) -> None:
    """API_KEY == API_ID -> base error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"

    user_input = {
        API_ID: "same",
        API_KEY: "same",
        WSLINK: False,
        DEV_DBG: False,
    }
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=user_input
    )
    assert result2["type"] == "form"
    assert result2["step_id"] == "user"
    assert result2["errors"]["base"] == "valid_credentials_match"


@pytest.mark.asyncio
async def test_options_flow_init_menu(hass, enable_custom_integrations) -> None:
    """Options flow shows menu with expected steps."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    assert result["step_id"] == "init"
    assert set(result["menu_options"]) == {"basic", "ecowitt", "windy", "pocasi"}


@pytest.mark.asyncio
async def test_options_flow_basic_validation_and_create_entry(
    hass, enable_custom_integrations
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            API_ID: "old",
            API_KEY: "oldkey",
            WSLINK: False,
            DEV_DBG: False,
        },
    )
    entry.add_to_hass(hass)

    init = await hass.config_entries.options.async_init(entry.entry_id)
    assert init["type"] == "menu"

    form = await hass.config_entries.options.async_configure(
        init["flow_id"], user_input={"next_step_id": "basic"}
    )
    assert form["type"] == "form"
    assert form["step_id"] == "basic"

    # Cover invalid API_ID branch in options flow basic step.
    bad_api_id = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={
            API_ID: INVALID_CREDENTIALS[0],
            API_KEY: "ok_key",
            WSLINK: False,
            DEV_DBG: False,
        },
    )
    assert bad_api_id["type"] == "form"
    assert bad_api_id["step_id"] == "basic"
    assert bad_api_id["errors"][API_ID] == "valid_credentials_api"

    # Cover invalid API_KEY branch in options flow basic step.
    bad_api_key = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={
            API_ID: "ok_id",
            API_KEY: INVALID_CREDENTIALS[0],
            WSLINK: False,
            DEV_DBG: False,
        },
    )
    assert bad_api_key["type"] == "form"
    assert bad_api_key["step_id"] == "basic"
    assert bad_api_key["errors"][API_KEY] == "valid_credentials_key"

    bad = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={API_ID: "same", API_KEY: "same", WSLINK: False, DEV_DBG: False},
    )
    assert bad["type"] == "form"
    assert bad["step_id"] == "basic"
    assert bad["errors"]["base"] == "valid_credentials_match"

    good = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={API_ID: "new", API_KEY: "newkey", WSLINK: True, DEV_DBG: True},
    )
    assert good["type"] == "create_entry"
    assert good["title"] == DOMAIN
    assert good["data"][API_ID] == "new"
    assert good["data"][API_KEY] == "newkey"
    assert good["data"][WSLINK] is True
    assert good["data"][DEV_DBG] is True


@pytest.mark.asyncio
async def test_options_flow_windy_requires_keys_when_enabled(
    hass, enable_custom_integrations
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            WINDY_ENABLED: False,
            WINDY_LOGGER_ENABLED: False,
            WINDY_STATION_ID: "",
            WINDY_STATION_PW: "",
        },
    )
    entry.add_to_hass(hass)

    init = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        init["flow_id"], user_input={"next_step_id": "windy"}
    )
    assert form["type"] == "form"
    assert form["step_id"] == "windy"

    bad = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={
            WINDY_ENABLED: True,
            WINDY_LOGGER_ENABLED: False,
            WINDY_STATION_ID: "",
            WINDY_STATION_PW: "",
        },
    )
    assert bad["type"] == "form"
    assert bad["step_id"] == "windy"
    assert bad["errors"][WINDY_STATION_ID] == "windy_key_required"

    good = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={
            WINDY_ENABLED: True,
            WINDY_LOGGER_ENABLED: True,
            WINDY_STATION_ID: "sid",
            WINDY_STATION_PW: "spw",
        },
    )
    assert good["type"] == "create_entry"
    assert good["data"][WINDY_ENABLED] is True


@pytest.mark.asyncio
async def test_options_flow_pocasi_validation_minimum_interval_and_required_keys(
    hass,
    enable_custom_integrations,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            POCASI_CZ_API_ID: "",
            POCASI_CZ_API_KEY: "",
            POCASI_CZ_ENABLED: False,
            POCASI_CZ_LOGGER_ENABLED: False,
            POCASI_CZ_SEND_INTERVAL: 30,
        },
    )
    entry.add_to_hass(hass)

    init = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        init["flow_id"], user_input={"next_step_id": "pocasi"}
    )
    assert form["type"] == "form"
    assert form["step_id"] == "pocasi"

    bad = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={
            POCASI_CZ_API_ID: "",
            POCASI_CZ_API_KEY: "",
            POCASI_CZ_ENABLED: True,
            POCASI_CZ_LOGGER_ENABLED: False,
            POCASI_CZ_SEND_INTERVAL: POCASI_CZ_SEND_MINIMUM - 1,
        },
    )
    assert bad["type"] == "form"
    assert bad["step_id"] == "pocasi"
    assert bad["errors"][POCASI_CZ_SEND_INTERVAL] == "pocasi_send_minimum"
    assert bad["errors"][POCASI_CZ_API_ID] == "pocasi_id_required"
    assert bad["errors"][POCASI_CZ_API_KEY] == "pocasi_key_required"

    good = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={
            POCASI_CZ_API_ID: "pid",
            POCASI_CZ_API_KEY: "pkey",
            POCASI_CZ_ENABLED: True,
            POCASI_CZ_LOGGER_ENABLED: True,
            POCASI_CZ_SEND_INTERVAL: POCASI_CZ_SEND_MINIMUM,
        },
    )
    assert good["type"] == "create_entry"
    assert good["data"][POCASI_CZ_ENABLED] is True


@pytest.mark.asyncio
async def test_options_flow_ecowitt_uses_get_url_placeholders_and_webhook_default(
    hass,
    enable_custom_integrations,
) -> None:
    """Online HA: ecowitt step uses get_url() placeholders and secrets token when webhook id missing."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            ECOWITT_WEBHOOK_ID: "",
            ECOWITT_ENABLED: False,
        },
    )
    entry.add_to_hass(hass)

    init = await hass.config_entries.options.async_init(entry.entry_id)
    assert init["type"] == "menu"

    # NOTE:
    # The integration currently attempts to mutate `yarl.URL.host` when it is missing:
    #
    #     url: URL = URL(get_url(self.hass))
    #     if not url.host:
    #         url.host = "UNKNOWN"
    #
    # With current yarl versions, `URL.host` is a cached, read-only property, so this
    # raises `AttributeError: cached property is read-only`.
    #
    # We assert that behavior explicitly to keep coverage deterministic and document the
    # runtime incompatibility. If the integration code is updated to handle missing hosts
    # without mutation (e.g. using `url.raw_host` or building placeholders without setting
    # attributes), this assertion should be updated accordingly.
    with patch(
        "custom_components.sws12500.config_flow.get_url",
        return_value="http://",
    ):
        with pytest.raises(AttributeError):
            await hass.config_entries.options.async_configure(
                init["flow_id"], user_input={"next_step_id": "ecowitt"}
            )

    # Second call uses a normal URL and completes the flow.
    with patch(
        "custom_components.sws12500.config_flow.get_url",
        return_value="http://example.local:8123",
    ):
        form = await hass.config_entries.options.async_configure(
            init["flow_id"], user_input={"next_step_id": "ecowitt"}
        )
        assert form["type"] == "form"
        assert form["step_id"] == "ecowitt"
        placeholders = form.get("description_placeholders") or {}
        assert placeholders["url"] == "example.local"
        assert placeholders["port"] == "8123"
        assert placeholders["webhook_id"]  # generated

        done = await hass.config_entries.options.async_configure(
            init["flow_id"],
            user_input={
                ECOWITT_WEBHOOK_ID: placeholders["webhook_id"],
                ECOWITT_ENABLED: True,
            },
        )
        assert done["type"] == "create_entry"
        assert done["data"][ECOWITT_ENABLED] is True
