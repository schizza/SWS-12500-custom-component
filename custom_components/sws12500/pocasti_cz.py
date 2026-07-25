"""Pocasi CZ resend functions."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Literal

from aiohttp import ClientError
from py_typecheck.core import checked

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_URL,
    POCASI_CZ_API_ID,
    POCASI_CZ_API_KEY,
    POCASI_CZ_ENABLED,
    POCASI_CZ_LOGGER_ENABLED,
    POCASI_CZ_MAX_RETRIES,
    POCASI_CZ_SEND_INTERVAL,
    POCASI_CZ_SUCCESS,
    POCASI_CZ_UNEXPECTED,
    POCASI_CZ_URL,
    POCASI_INVALID_KEY,
    WSLINK_URL,
)
from .utils import anonymize, update_options

_LOGGER = logging.getLogger(__name__)

# Outcome of a single send, derived from the HTTP status (see `verify_response`).
type PocasiResult = Literal["ok", "auth_error", "unexpected_response"]


class PocasiPush:
    """Forward station payloads to the Pocasi Meteo server."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Init."""
        self.hass = hass
        self.config = config
        self.enabled: bool = self.config.options.get(POCASI_CZ_ENABLED, False)
        self.last_status: str = "disabled" if not self.enabled else "idle"
        self.last_error: str | None = None
        self.last_attempt_at: str | None = None
        self._interval = int(self.config.options.get(POCASI_CZ_SEND_INTERVAL, 30))

        self.last_update = dt_util.utcnow()
        self.next_update = dt_util.utcnow() + timedelta(seconds=self._interval)

        self.log = self.config.options.get(POCASI_CZ_LOGGER_ENABLED)
        self.invalid_response_count = 0

    def verify_response(self, status: int, body: str) -> PocasiResult:
        """Classify a send by its HTTP status.

        The server returns no meaningful body, so the status code is all we have:
        - 2xx           -> "ok"
        - 401 / 403     -> "auth_error" (bad ID/key combination)
        - anything else -> "unexpected_response", counted toward the retry limit
        """

        if self.log:
            _LOGGER.debug("Pocasi CZ responded: [%s] %s", status, body)

        if 200 <= status < 300:
            return "ok"
        if status in (401, 403):
            return "auth_error"
        return "unexpected_response"

    async def _disable_pocasi(self, reason: str) -> None:
        """Turn resending off and persist it, so it survives a restart."""

        self.enabled = False
        self.last_error = reason

        if not await update_options(self.hass, self.config, POCASI_CZ_ENABLED, False):
            _LOGGER.debug("Failed to set Pocasi Meteo options to false.")

    async def push_data_to_server(self, data: dict[str, Any], mode: Literal["WU", "WSLINK"]):
        """Pushes weather data to server."""

        _data = data.copy()
        self.enabled = self.config.options.get(POCASI_CZ_ENABLED, False)
        self.last_attempt_at = dt_util.utcnow().isoformat()
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

        if self.next_update > dt_util.utcnow():
            self.last_status = "rate_limited_local"
            _LOGGER.debug(
                "Triggered update interval limit of %s seconds. Next possilbe update is set to: %s",
                self._interval,
                self.next_update,
            )
            return

        # Reserve the next send window before the await to avoid concurrent double-sends.
        self.next_update = dt_util.utcnow() + timedelta(seconds=self._interval)

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
                result = self.verify_response(resp.status, await resp.text())
                http_status = resp.status

            if result == "ok":
                self.invalid_response_count = 0
                self.last_status = "ok"
                self.last_error = None
                if self.log:
                    _LOGGER.info(POCASI_CZ_SUCCESS)

            elif result == "auth_error":
                # Credentials will not fix themselves - disable immediately instead of
                # burning through the retry budget. Logged regardless of the log setting.
                self.last_status = "auth_error"
                _LOGGER.critical(POCASI_INVALID_KEY)
                await self._disable_pocasi(POCASI_INVALID_KEY)

            else:
                self.last_status = "unexpected_response"
                self.last_error = f"Unexpected HTTP status {http_status} from Pocasi Meteo."
                self.invalid_response_count += 1
                _LOGGER.warning(
                    "Unexpected HTTP status %s from Pocasi Meteo. Retries before disabling resend: %s",
                    http_status,
                    POCASI_CZ_MAX_RETRIES - self.invalid_response_count,
                )
                if self.invalid_response_count >= POCASI_CZ_MAX_RETRIES:
                    _LOGGER.critical(POCASI_CZ_UNEXPECTED)
                    await self._disable_pocasi(POCASI_CZ_UNEXPECTED)

        except ClientError as ex:
            self.last_status = "client_error"
            # Store only the exception class - last_error is surfaced via entity
            # attributes; str(ex) could embed the request URL.
            self.last_error = type(ex).__name__
            _LOGGER.critical("Invalid response from Pocasi Meteo: %s", str(ex))
            self.invalid_response_count += 1
            if self.invalid_response_count >= POCASI_CZ_MAX_RETRIES:
                _LOGGER.critical(POCASI_CZ_UNEXPECTED)
                await self._disable_pocasi(POCASI_CZ_UNEXPECTED)

        self.last_update = dt_util.utcnow()
        self.next_update = dt_util.utcnow() + timedelta(seconds=self._interval)

        if self.log:
            _LOGGER.info("Next update: %s", str(self.next_update))
