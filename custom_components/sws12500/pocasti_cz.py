"""Pocasi CZ resend functions."""

from __future__ import annotations

from datetime import timedelta
from functools import partial
import logging
from typing import Any, Literal

from aiohttp import ClientError, ClientTimeout
from py_typecheck.core import checked_or

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_URL,
    FORWARD_TIMEOUT,
    POCASI_CZ_API_ID,
    POCASI_CZ_API_KEY,
    POCASI_CZ_ECOWITT_ID_PARAM,
    POCASI_CZ_ECOWITT_PW_PARAM,
    POCASI_CZ_ECOWITT_URL,
    POCASI_CZ_ENABLED,
    POCASI_CZ_LOGGER_ENABLED,
    POCASI_CZ_MAX_RETRIES,
    POCASI_CZ_SEND_DEFAULT,
    POCASI_CZ_SEND_INTERVAL,
    POCASI_CZ_SUCCESS,
    POCASI_CZ_UNEXPECTED,
    POCASI_CZ_URL,
    POCASI_INVALID_KEY,
    WSLINK_URL,
)
from .utils import anonymize, to_int, update_options

_LOGGER = logging.getLogger(__name__)

# Outcome of a single send, derived from the HTTP status (see `verify_response`).
type PocasiResult = Literal["ok", "auth_error", "unexpected_response"]

# Which upstream protocol a payload is forwarded in.
type PocasiMode = Literal["WU", "WSLINK", "ECOWITT"]


class PocasiPush:
    """Forward station payloads to the Pocasi Meteo server."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Init."""
        self.hass = hass
        self.config = config
        self.last_status: str = "disabled" if not self.enabled else "idle"
        self.last_error: str | None = None
        self.last_attempt_at: str | None = None
        # A stored interval that does not parse falls back to the default rather than
        # raising here, which would take the whole config entry setup down.
        self._interval = to_int(self.config.options.get(POCASI_CZ_SEND_INTERVAL)) or POCASI_CZ_SEND_DEFAULT

        self.last_update = dt_util.utcnow()
        self.next_update = dt_util.utcnow() + timedelta(seconds=self._interval)

        self.log = self.config.options.get(POCASI_CZ_LOGGER_ENABLED)
        self.invalid_response_count = 0

    @property
    def enabled(self) -> bool:
        """Whether forwarding is currently on, read live from the options.

        Toggling this option does not reload the entry (see `update_listener`), so a
        cached copy would leave the diagnostics sensor reporting a stale value until
        the next push - or forever, since a disabled forwarder is never called again.
        """
        return checked_or(self.config.options.get(POCASI_CZ_ENABLED), bool, False)

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
        """Turn resending off and persist it, so it survives a restart.

        Notifies the user as well - as `WindyPush._disable_windy` does. Forwarding
        switching itself off is otherwise invisible until someone notices that data
        stopped arriving upstream, since the only other trace is a log line.
        """

        self.last_error = reason

        if not await update_options(self.hass, self.config, POCASI_CZ_ENABLED, False):
            _LOGGER.debug("Failed to set Pocasi Meteo options to false.")

        persistent_notification.async_create(self.hass, reason, "Pocasi Meteo resending disabled.")

    async def push_data_to_server(self, data: dict[str, Any], mode: PocasiMode):
        """Forward a station payload to Pocasi Meteo.

        WU and WSLINK are GET requests carrying the readings as query parameters.
        ECOWITT is a POST of the station's own payload with the credentials in the
        query string - the server only accepts the Ecowitt protocol that way.
        """

        _data = data.copy()
        self.last_attempt_at = dt_util.utcnow().isoformat()
        self.last_error = None

        # An empty string is still a `str`, so `checked` alone would let unconfigured
        # credentials through and send a request that can only ever be rejected.
        if not (_api_id := checked_or(self.config.options.get(POCASI_CZ_API_ID), str, "")):
            _LOGGER.error("No API ID is provided for Pocasi Meteo. Check your configuration.")
            self.last_status = "config_error"
            self.last_error = "Missing API ID."
            return

        if not (_api_key := checked_or(self.config.options.get(POCASI_CZ_API_KEY), str, "")):
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
                "Triggered update interval limit of %s seconds. Next possible update is set to: %s",
                self._interval,
                self.next_update,
            )
            return

        # Reserve the next send window before the await to avoid concurrent double-sends.
        self.next_update = dt_util.utcnow() + timedelta(seconds=self._interval)

        session = async_get_clientsession(self.hass)
        request_url: str = ""
        params: dict[str, Any] = {}

        # Home Assistant's shared session sets no timeout, so without an explicit one a
        # stalled server would hold the station's webhook open for aiohttp's 5 minute
        # default and the TimeoutError branch below could never run in time to answer
        # the station.
        timeout = ClientTimeout(total=FORWARD_TIMEOUT)

        if mode == "ECOWITT":
            # Pocasi Meteo takes Ecowitt only as a POST in the Ecowitt protocol itself,
            # so the station payload is forwarded verbatim; only the credentials are
            # ours, and they travel in the query string as ID / PAS.
            request_url = f"{POCASI_CZ_URL}{POCASI_CZ_ECOWITT_URL}"
            params = {
                POCASI_CZ_ECOWITT_ID_PARAM: _api_id,
                POCASI_CZ_ECOWITT_PW_PARAM: _api_key,
            }
            make_request = partial(session.post, request_url, params=params, data=_data, timeout=timeout)
        else:
            if mode == "WSLINK":
                _data["wsid"] = _api_id
                _data["wspw"] = _api_key
                request_url = f"{POCASI_CZ_URL}{WSLINK_URL}"
            else:
                _data["ID"] = _api_id
                _data["PASSWORD"] = _api_key
                request_url = f"{POCASI_CZ_URL}{DEFAULT_URL}"

            make_request = partial(session.get, request_url, params=_data, timeout=timeout)

        _LOGGER.debug(
            "Payload for Pocasi Meteo server: [mode=%s] [request_url=%s] [params=%s] = %s",
            mode,
            request_url,
            anonymize(params),
            anonymize(_data),
        )
        try:
            # Built inside the try: a failure while creating the request must be handled
            # like any other transport error, not escape into the webhook handler.
            async with make_request() as resp:
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

        # TimeoutError is not a ClientError: an `async_timeout`/`asyncio` timeout would
        # otherwise escape into the webhook handler and answer the station with HTTP 500,
        # even though the measured data was already stored.
        #
        # It gets its own branch because it must not spend the retry budget: a slow
        # upstream is transient and self-healing, so the next push just tries again,
        # while `invalid_response_count` is meant for faults that will not fix
        # themselves. Caught first on purpose - aiohttp's ServerTimeoutError is both a
        # ClientError and a TimeoutError, and it belongs here.
        except TimeoutError as ex:
            self.last_status = "timeout"
            self.last_error = type(ex).__name__
            _LOGGER.warning(
                "Pocasi Meteo did not answer within %s seconds. Will try again on the next push.",
                FORWARD_TIMEOUT,
            )
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
