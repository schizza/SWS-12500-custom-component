"""Pocasi CZ resend functions."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, Literal

from aiohttp import ClientError
from py_typecheck.core import checked

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DEFAULT_URL,
    POCASI_CZ_API_ID,
    POCASI_CZ_API_KEY,
    POCASI_CZ_ENABLED,
    POCASI_CZ_LOGGER_ENABLED,
    POCASI_CZ_SEND_INTERVAL,
    POCASI_CZ_SUCCESS,
    POCASI_CZ_UNEXPECTED,
    POCASI_CZ_URL,
    POCASI_INVALID_KEY,
    WSLINK_URL,
)
from .utils import anonymize, update_options

_LOGGER = logging.getLogger(__name__)


class PocasiNotInserted(Exception):
    """NotInserted state."""


class PocasiSuccess(Exception):
    """WindySucces state."""


class PocasiApiKeyError(Exception):
    """Windy API Key error."""


class PocasiPush:
    """Push data to Windy."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Init."""
        self.hass = hass
        self.config = config
        self.enabled: bool = self.config.options.get(POCASI_CZ_ENABLED, False)
        self.last_status: str = "disabled" if not self.enabled else "idle"
        self.last_error: str | None = None
        self.last_attempt_at: str | None = None
        self._interval = int(self.config.options.get(POCASI_CZ_SEND_INTERVAL, 30))

        self.last_update = datetime.now()
        self.next_update = datetime.now() + timedelta(seconds=self._interval)

        self.log = self.config.options.get(POCASI_CZ_LOGGER_ENABLED)
        self.invalid_response_count = 0

    def verify_response(
        self,
        response: str,
    ) -> PocasiNotInserted | PocasiSuccess | PocasiApiKeyError | None:
        """Verify answer form server."""

        if self.log:
            _LOGGER.debug("Pocasi CZ responded: %s", response)

        # Server does not provide any responses.
        # This is placeholder if future state is changed

        return None

    async def push_data_to_server(self, data: dict[str, Any], mode: Literal["WU", "WSLINK"]):
        """Pushes weather data to server."""

        _data = data.copy()
        self.enabled = self.config.options.get(POCASI_CZ_ENABLED, False)
        self.last_attempt_at = datetime.now().isoformat()
        self.last_error = None

        if (_api_id := checked(self.config.options.get(POCASI_CZ_API_ID), str)) is None:
            _LOGGER.error("No API ID is provided for Pocasi Meteo. Check your configuration.")
            self.last_status = "config_error"
            self.last_error = "Missing API ID."
            return

        if (_api_key := checked(self.config.options.get(POCASI_CZ_API_KEY), str)) is None:
            _LOGGER.error("No API Key is provided for Pocasi Meteo. Check your configuration.")
            self.last_status = "config_error"
            self.last_error = "Missing API key."
            return

        if self.log:
            _LOGGER.info(
                "Pocasi CZ last update = %s, next update at: %s",
                str(self.last_update),
                str(self.next_update),
            )

        if self.next_update > datetime.now():
            self.last_status = "rate_limited_local"
            _LOGGER.debug(
                "Triggered update interval limit of %s seconds. Next possilbe update is set to: %s",
                self._interval,
                self.next_update,
            )
            return

        request_url: str = ""
        if mode == "WSLINK":
            _data["wsid"] = _api_id
            _data["wspw"] = _api_key
            request_url = f"{POCASI_CZ_URL}{WSLINK_URL}"

        if mode == "WU":
            _data["ID"] = _api_id
            _data["PASSWORD"] = _api_key
            request_url = f"{POCASI_CZ_URL}{DEFAULT_URL}"

        session = async_get_clientsession(self.hass)
        _LOGGER.debug(
            "Payload for Pocasi Meteo server: [mode=%s] [request_url=%s] = %s",
            mode,
            request_url,
            anonymize(_data),
        )
        try:
            async with session.get(request_url, params=_data) as resp:
                status = await resp.text()
                try:
                    self.verify_response(status)

                except PocasiApiKeyError:
                    # log despite of settings
                    self.last_status = "auth_error"
                    self.last_error = POCASI_INVALID_KEY
                    self.enabled = False
                    _LOGGER.critical(POCASI_INVALID_KEY)
                    await update_options(self.hass, self.config, POCASI_CZ_ENABLED, False)
                except PocasiSuccess:
                    self.last_status = "ok"
                    self.last_error = None
                    if self.log:
                        _LOGGER.info(POCASI_CZ_SUCCESS)
                else:
                    self.last_status = "ok"

        except ClientError as ex:
            self.last_status = "client_error"
            self.last_error = str(ex)
            _LOGGER.critical("Invalid response from Pocasi Meteo: %s", str(ex))
            self.invalid_response_count += 1
            if self.invalid_response_count > 3:
                _LOGGER.critical(POCASI_CZ_UNEXPECTED)
                self.enabled = False
                await update_options(self.hass, self.config, POCASI_CZ_ENABLED, False)

        self.last_update = datetime.now()
        self.next_update = datetime.now() + timedelta(seconds=self._interval)

        if self.log:
            _LOGGER.info("Next update: %s", str(self.next_update))
