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
    LEGACY_ENABLED,
    POCASI_CZ_API_ID,
    POCASI_CZ_API_KEY,
    POCASI_CZ_ENABLED,
    POCASI_CZ_LOGGER_ENABLED,
    POCASI_CZ_SEND_INTERVAL,
    POCASI_CZ_SEND_MINIMUM,
    SENSORS_TO_LOAD,
    WINDY_ENABLED,
    WINDY_LOGGER_ENABLED,
    WINDY_STATION_ID,
    WINDY_STATION_PW,
    WSLINK,
    WSLINK_ADDON_PORT,
)
from homeassistant import config_entries
from homeassistant.helpers.network import NoURLAvailableError


@pytest.mark.asyncio
async def test_config_flow_user_form_then_create_entry(
    hass, enable_custom_integrations
) -> None:
    """Online HA: config flow shows form then creates entry and options."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "menu"
    assert result["step_id"] == "user"

    form = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "pws"}
    )
    assert form["type"] == "form"
    assert form["step_id"] == "pws"

    user_input = {
        API_ID: "my_id",
        API_KEY: "my_key",
        WSLINK: False,
        DEV_DBG: False,
    }
    result2 = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input=user_input
    )
    assert result2["type"] == "create_entry"
    assert result2["title"] == DOMAIN
    # The PWS step augments user input with legacy/ecowitt flags.
    assert result2["data"][API_ID] == "my_id"
    assert result2["data"][API_KEY] == "my_key"
    assert result2["data"][LEGACY_ENABLED] is True
    assert result2["data"][ECOWITT_ENABLED] is False
    assert result2["options"] == result2["data"]


@pytest.mark.asyncio
async def test_config_flow_user_invalid_credentials_api_id(
    hass, enable_custom_integrations
) -> None:
    """API_ID in INVALID_CREDENTIALS -> error on API_ID."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "menu"

    form = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "pws"}
    )
    assert form["type"] == "form"
    assert form["step_id"] == "pws"

    user_input = {
        API_ID: INVALID_CREDENTIALS[0],
        API_KEY: "ok_key",
        WSLINK: False,
        DEV_DBG: False,
    }
    result2 = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input=user_input
    )
    assert result2["type"] == "form"
    assert result2["step_id"] == "pws"
    assert result2["errors"][API_ID] == "valid_credentials_api"


@pytest.mark.asyncio
async def test_config_flow_user_invalid_credentials_api_key(
    hass, enable_custom_integrations
) -> None:
    """API_KEY in INVALID_CREDENTIALS -> error on API_KEY."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "menu"

    form = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "pws"}
    )
    assert form["type"] == "form"
    assert form["step_id"] == "pws"

    user_input = {
        API_ID: "ok_id",
        API_KEY: INVALID_CREDENTIALS[0],
        WSLINK: False,
        DEV_DBG: False,
    }
    result2 = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input=user_input
    )
    assert result2["type"] == "form"
    assert result2["step_id"] == "pws"
    assert result2["errors"][API_KEY] == "valid_credentials_key"


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize("field", [API_ID, API_KEY])
@pytest.mark.asyncio
async def test_config_flow_user_rejects_blank_credentials(
    hass, enable_custom_integrations, field, blank
) -> None:
    """Blank PWS credentials must not create an entry.

    `INVALID_CREDENTIALS` holds placeholder strings only, so an empty (or
    whitespace-only) value used to pass validation. The entry was created but
    `_validate_credentials` then rejected every incoming packet, leaving the
    integration permanently without data.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    form = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "pws"}
    )
    assert form["step_id"] == "pws"

    user_input = {
        API_ID: "ok_id",
        API_KEY: "ok_key",
        WSLINK: False,
        DEV_DBG: False,
    }
    user_input[field] = blank

    result2 = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input=user_input
    )
    assert result2["type"] == "form"
    assert result2["step_id"] == "pws"
    expected = "valid_credentials_api" if field is API_ID else "valid_credentials_key"
    assert result2["errors"][field] == expected


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize("field", [API_ID, API_KEY])
@pytest.mark.asyncio
async def test_options_flow_basic_rejects_blank_credentials(
    hass, enable_custom_integrations, field, blank
) -> None:
    """Same blank-credential rule applies when the legacy endpoint is re-enabled."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={LEGACY_ENABLED: False, ECOWITT_ENABLED: False},
    )
    entry.add_to_hass(hass)

    init = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        init["flow_id"], user_input={"next_step_id": "basic"}
    )
    assert form["step_id"] == "basic"

    user_input = {
        API_ID: "ok_id",
        API_KEY: "ok_key",
        WSLINK: False,
        DEV_DBG: False,
        LEGACY_ENABLED: True,
    }
    user_input[field] = blank

    result = await hass.config_entries.options.async_configure(
        init["flow_id"], user_input=user_input
    )
    assert result["type"] == "form"
    expected = "valid_credentials_api" if field is API_ID else "valid_credentials_key"
    assert result["errors"][field] == expected


@pytest.mark.asyncio
async def test_config_flow_user_invalid_credentials_match(
    hass, enable_custom_integrations
) -> None:
    """API_KEY == API_ID -> base error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "menu"

    form = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "pws"}
    )
    assert form["type"] == "form"
    assert form["step_id"] == "pws"

    user_input = {
        API_ID: "same",
        API_KEY: "same",
        WSLINK: False,
        DEV_DBG: False,
    }
    result2 = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input=user_input
    )
    assert result2["type"] == "form"
    assert result2["step_id"] == "pws"
    assert result2["errors"]["base"] == "valid_credentials_match"


@pytest.mark.parametrize(
    ("user_input", "field", "error"),
    [
        ({API_ID: "", API_KEY: "ok_key", WSLINK: False, DEV_DBG: False}, API_ID, "valid_credentials_api"),
        ({API_ID: "ok_id", API_KEY: "", WSLINK: False, DEV_DBG: False}, API_KEY, "valid_credentials_key"),
    ],
)
@pytest.mark.asyncio
async def test_config_flow_user_rejects_empty_pws_credentials(
    hass,
    enable_custom_integrations,
    user_input,
    field,
    error,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    form = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "pws"}
    )

    result2 = await hass.config_entries.flow.async_configure(form["flow_id"], user_input=user_input)

    assert result2["type"] == "form"
    assert result2["step_id"] == "pws"
    assert result2["errors"][field] == error


@pytest.mark.asyncio
async def test_options_flow_init_menu(hass, enable_custom_integrations) -> None:
    """Options flow shows menu with expected steps."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    assert result["step_id"] == "init"
    assert set(result["menu_options"]) == {"basic", "wslink_port_setup", "ecowitt", "windy", "pocasi"}


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
            # Ecowitt can only be turned on when the legacy endpoint is off.
            LEGACY_ENABLED: False,
        },
    )
    entry.add_to_hass(hass)

    # A URL without a host degrades to the "UNKNOWN" placeholder rather than raising.
    # (`yarl.URL.host` is a read-only cached property, so the fallback has to build a
    # new value instead of assigning to it.) This runs in its own flow because showing
    # the form advances past the menu.
    hostless_init = await hass.config_entries.options.async_init(entry.entry_id)
    assert hostless_init["type"] == "menu"

    with patch(
        "custom_components.sws12500.config_flow.get_url",
        return_value="http://",
    ):
        hostless = await hass.config_entries.options.async_configure(
            hostless_init["flow_id"], user_input={"next_step_id": "ecowitt"}
        )
        assert hostless["type"] == "form"
        assert (hostless.get("description_placeholders") or {})["url"] == "UNKNOWN"

    # A normal URL fills real placeholders and completes the flow.
    init = await hass.config_entries.options.async_init(entry.entry_id)
    assert init["type"] == "menu"

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

        bad = await hass.config_entries.options.async_configure(
            init["flow_id"],
            user_input={
                ECOWITT_WEBHOOK_ID: "",
                ECOWITT_ENABLED: True,
            },
        )
        assert bad["type"] == "form"
        assert bad["errors"][ECOWITT_WEBHOOK_ID] == "ecowitt_webhook_required"

        done = await hass.config_entries.options.async_configure(
            init["flow_id"],
            user_input={
                ECOWITT_WEBHOOK_ID: placeholders["webhook_id"],
                ECOWITT_ENABLED: True,
            },
        )
        assert done["type"] == "create_entry"
        assert done["data"][ECOWITT_ENABLED] is True


@pytest.mark.asyncio
async def test_options_flow_ecowitt_survives_no_url_available(
    hass, enable_custom_integrations
) -> None:
    """`get_url` raising must not abort the Ecowitt options step.

    The host/port are shown as setup instructions only. HA can fail to resolve any
    of its own URLs (no internal/external URL configured), and letting that escape
    made the Ecowitt setup unreachable.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={ECOWITT_WEBHOOK_ID: "", ECOWITT_ENABLED: False, LEGACY_ENABLED: False},
    )
    entry.add_to_hass(hass)

    init = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(
        "custom_components.sws12500.config_flow.get_url",
        side_effect=NoURLAvailableError,
    ):
        form = await hass.config_entries.options.async_configure(
            init["flow_id"], user_input={"next_step_id": "ecowitt"}
        )
    assert form["type"] == "form"
    placeholders = form.get("description_placeholders") or {}
    assert placeholders["url"] == "UNKNOWN"
    assert placeholders["port"] == "UNKNOWN"
    assert placeholders["webhook_id"]


@pytest.mark.asyncio
async def test_config_flow_ecowitt_survives_no_url_available(
    hass, enable_custom_integrations
) -> None:
    """The initial Ecowitt step stays usable when HA cannot resolve its own URL."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.sws12500.config_flow.get_url",
        side_effect=NoURLAvailableError,
    ):
        form = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"next_step_id": "ecowitt"}
        )
    assert form["type"] == "form"
    placeholders = form.get("description_placeholders") or {}
    assert placeholders["url"] == "UNKNOWN"
    assert placeholders["port"] == "UNKNOWN"

    # The step is still completable without a resolvable URL.
    done = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        user_input={
            ECOWITT_WEBHOOK_ID: placeholders["webhook_id"],
            ECOWITT_ENABLED: True,
        },
    )
    assert done["type"] == "create_entry"
    assert done["data"][ECOWITT_ENABLED] is True


@pytest.mark.asyncio
async def test_options_flow_wslink_port_setup(hass, enable_custom_integrations) -> None:
    """The WSLink add-on port step shows a form and stores the port."""
    # A falsy stored port exercises the 443 default fallback.
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={WSLINK_ADDON_PORT: 0})
    entry.add_to_hass(hass)

    init = await hass.config_entries.options.async_init(entry.entry_id)
    assert init["type"] == "menu"

    form = await hass.config_entries.options.async_configure(
        init["flow_id"], user_input={"next_step_id": "wslink_port_setup"}
    )
    assert form["type"] == "form"
    assert form["step_id"] == "wslink_port_setup"

    done = await hass.config_entries.options.async_configure(
        init["flow_id"], user_input={WSLINK_ADDON_PORT: 8443}
    )
    assert done["type"] == "create_entry"
    assert done["data"][WSLINK_ADDON_PORT] == 8443


@pytest.mark.asyncio
async def test_config_flow_ecowitt_initial_setup(hass, enable_custom_integrations) -> None:
    """Initial config flow: user menu -> ecowitt step creates an Ecowitt-only entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "menu"

    with patch(
        "custom_components.sws12500.config_flow.get_url",
        return_value="http://example.local:8123",
    ):
        form = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"next_step_id": "ecowitt"}
        )
        assert form["type"] == "form"
        assert form["step_id"] == "ecowitt"
        placeholders = form.get("description_placeholders") or {}
        assert placeholders["url"] == "example.local"
        assert placeholders["webhook_id"]

        bad = await hass.config_entries.flow.async_configure(
            form["flow_id"],
            user_input={
                ECOWITT_WEBHOOK_ID: "",
                ECOWITT_ENABLED: True,
            },
        )
        assert bad["type"] == "form"
        assert bad["errors"][ECOWITT_WEBHOOK_ID] == "ecowitt_webhook_required"

        done = await hass.config_entries.flow.async_configure(
            form["flow_id"],
            user_input={
                ECOWITT_WEBHOOK_ID: placeholders["webhook_id"],
                ECOWITT_ENABLED: True,
            },
        )
        assert done["type"] == "create_entry"
        assert done["data"][ECOWITT_ENABLED] is True
        assert done["data"][LEGACY_ENABLED] is False


@pytest.mark.asyncio
async def test_options_flow_does_not_roll_back_concurrent_autodiscovery(
    hass,
    enable_custom_integrations,
) -> None:
    """Auto-discovery that lands while the dialog is open must survive the submit.

    The options flow snapshots the entry when a step opens, but the webhook handler
    appends to SENSORS_TO_LOAD independently. Writing back the snapshot would silently
    drop any sensor discovered in between.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            API_ID: "station",
            API_KEY: "secret",
            LEGACY_ENABLED: True,
            SENSORS_TO_LOAD: ["outside_temp"],
        },
    )
    entry.add_to_hass(hass)

    init = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(init["flow_id"], user_input={"next_step_id": "basic"})

    # The station starts reporting a new field while the form is on screen.
    hass.config_entries.async_update_entry(
        entry,
        options={**entry.options, SENSORS_TO_LOAD: ["outside_temp", "wind_gust"]},
    )

    done = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={
            API_ID: "station",
            API_KEY: "secret",
            WSLINK: False,
            LEGACY_ENABLED: True,
        },
    )

    assert done["type"] == "create_entry"
    assert done["data"][SENSORS_TO_LOAD] == ["outside_temp", "wind_gust"]


@pytest.mark.asyncio
async def test_options_flow_keeps_the_learned_probe_types(
    hass,
    enable_custom_integrations,
) -> None:
    """Probe types are written from the hot path, like SENSORS_TO_LOAD.

    Dropping them on submit would silently turn every soil channel back into an
    air-humidity entity on the next restart.
    """
    from custom_components.sws12500.const import CHANNEL_TYPES

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            API_ID: "station",
            API_KEY: "secret",
            LEGACY_ENABLED: True,
            CHANNEL_TYPES: {"t234c1tp": "4"},
        },
    )
    entry.add_to_hass(hass)

    init = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(init["flow_id"], user_input={"next_step_id": "basic"})

    done = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={
            API_ID: "station",
            API_KEY: "secret",
            WSLINK: True,
            LEGACY_ENABLED: True,
        },
    )

    assert done["type"] == "create_entry"
    assert done["data"][CHANNEL_TYPES] == {"t234c1tp": "4"}
