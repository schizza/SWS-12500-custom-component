"""Windy functions."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Literal

from aiohttp.client import ClientResponse, ClientTimeout
from aiohttp.client_exceptions import ClientError
from py_typecheck import checked_or

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import (
    FORWARD_TIMEOUT,
    PURGE_DATA,
    WINDY_ENABLED,
    WINDY_INVALID_KEY,
    WINDY_LOGGER_ENABLED,
    WINDY_MAX_RETRIES,
    WINDY_NOT_INSERTED,
    WINDY_STATION_ID,
    WINDY_STATION_PW,
    WINDY_SUCCESS,
    WINDY_UNEXPECTED,
    WINDY_URL,
)
from .utils import remap_ecowitt_to_windy, update_options

_LOGGER = logging.getLogger(__name__)

# Which protocol the payload arrived in; Windy itself always speaks PWS.
type WindySource = Literal["pws", "wslink", "ecowitt"]


class WindyNotInserted(Exception):
    """NotInserted state.

    Possible variants are:
       - station password is invalid
       - station password does not match the station
       - payload failed validation
    """


class WindySuccess(Exception):
    """WindySucces state."""


class WindyPasswordMissing(Exception):
    """Windy password is missing in query or Authorization header.

    This should not happend, while we are checking if we have password set and do exits early.
    """


class WindyDuplicatePayloadDetected(Exception):
    """Duplicate payload detected."""


class WindyRateLimitExceeded(Exception):
    """Rate limit exceeded. Minimum interval is 5 minutes.

    This should not happend in runnig integration.
    Might be seen, if restart of HomeAssistant occured and we are not aware of previous update.
    """


def timed(minutes: int):
    """Simulate timedelta.

    So we can mock td in tests.
    """
    return timedelta(minutes=minutes)


class WindyPush:
    """Push data to Windy."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Init."""
        self.hass = hass
        self.config = config
        self.last_status: str = "disabled" if not self.enabled else "idle"
        self.last_error: str | None = None
        self.last_attempt_at: str | None = None

        """ lets wait for 1 minute to get initial data from station
            and then try to push first data to Windy
        """
        self.last_update: datetime = dt_util.utcnow()
        self.next_update: datetime = dt_util.utcnow() + timed(minutes=1)

        self.log: bool = self.config.options.get(WINDY_LOGGER_ENABLED, False)

        # Lets check if Windy server is responding right.
        # Otherwise, try WINDY_MAX_RETRIES times and then disable resending.
        self.invalid_response_count: int = 0

    @property
    def enabled(self) -> bool:
        """Whether forwarding is currently on, read live from the options.

        Toggling this option does not reload the entry (see `update_listener`), so a
        cached copy would leave the diagnostics sensor reporting a stale value until
        the next push - or forever, since a disabled forwarder is never called again.
        """
        return checked_or(self.config.options.get(WINDY_ENABLED), bool, False)

    # Refactored responses verification.
    #
    # We now comply to API at https://stations.windy.com/api-reference
    def verify_windy_response(self, response: ClientResponse):
        """Verify answer form Windy."""

        if self.log and response:
            # response.text is a coroutine; we are in a sync method here, so log the
            # status instead of awaiting/logging a bound method object.
            _LOGGER.info("Windy raw response status: %s", response.status)

        if response.status == 200:
            raise WindySuccess

        if response.status == 400:
            raise WindyNotInserted

        if response.status == 401:
            raise WindyPasswordMissing

        if response.status == 409:
            raise WindyDuplicatePayloadDetected

        if response.status == 429:
            raise WindyRateLimitExceeded

    def _to_pws(self, data: dict[str, str], source: WindySource) -> dict[str, str]:
        """Convert a station payload into the field names Windy understands.

        Windy speaks the PWS/WU vocabulary, so every other protocol has to be mapped
        onto it first. All three sources are dispatched here so the conversions stay
        in one place instead of being applied by whoever happens to call us.
        """
        if source == "wslink":
            return self._covert_wslink_to_pws(data)
        if source == "ecowitt":
            # Windy has no Ecowitt endpoint; the shared table also drops the station
            # metadata (PASSKEY, stationtype, model, ...) that means nothing upstream.
            return remap_ecowitt_to_windy(data)
        return data

    def _covert_wslink_to_pws(self, indata: dict[str, str]) -> dict[str, str]:
        """Convert WSLink API data to Windy API data protocol."""
        if "t1ws" in indata:
            indata["wind"] = indata.pop("t1ws")
        if "t1wgust" in indata:
            indata["gust"] = indata.pop("t1wgust")
        if "t1wdir" in indata:
            indata["winddir"] = indata.pop("t1wdir")
        if "t1hum" in indata:
            indata["humidity"] = indata.pop("t1hum")
        if "t1dew" in indata:
            indata["dewpoint"] = indata.pop("t1dew")
        if "t1tem" in indata:
            indata["temp"] = indata.pop("t1tem")
        if "rbar" in indata:
            indata["mbar"] = indata.pop("rbar")
        if "t1rainhr" in indata:
            indata["precip"] = indata.pop("t1rainhr")
        if "t1uvi" in indata:
            indata["uv"] = indata.pop("t1uvi")
        if "t1solrad" in indata:
            indata["solarradiation"] = indata.pop("t1solrad")
        # Indoor readings mean nothing to Windy. Renaming them to their PWS spelling
        # (rather than dropping them here) leaves PURGE_DATA - which lists PWS names -
        # as the single place that decides what Windy never receives, exactly as on the
        # Ecowitt path. The values stay Celsius/percent, which is fine because they are
        # purged before the request is built.
        if "intem" in indata:
            indata["indoortempf"] = indata.pop("intem")
        if "inhum" in indata:
            indata["indoorhumidity"] = indata.pop("inhum")

        return indata

    async def _disable_windy(self, reason: str) -> None:
        """Disable Windy resending.

        `enabled` reads the option back, so persisting it here is what actually turns
        forwarding off.

        `last_status` is deliberately left to the caller so the diagnostics sensor keeps
        the specific reason (`config_error`, `auth_error`, ...) instead of a generic one.
        """
        self.last_error = reason

        if not await update_options(self.hass, self.config, WINDY_ENABLED, False):
            _LOGGER.debug("Failed to set Windy options to false.")

        persistent_notification.async_create(self.hass, reason, "Windy resending disabled.")

    async def push_data_to_windy(self, data: dict[str, str], source: WindySource = "pws") -> bool:
        """Pushes weather data do Windy stations.

        Interval is 5 minutes, otherwise Windy would not accepts data.

        we are sending almost the same data as we received
        from station. But we need to do some clean up.
        """

        # First check if we have valid credentials, before any data manipulation.
        self.last_attempt_at = dt_util.utcnow().isoformat()
        self.last_error = None

        # An empty string is still a `str`, so `checked` alone would let unconfigured
        # credentials through and send a request that can only ever be rejected.
        if not (windy_station_id := checked_or(self.config.options.get(WINDY_STATION_ID), str, "")):
            _LOGGER.error("Windy station ID is not provided! Check your configuration.")
            self.last_status = "config_error"
            await self._disable_windy(
                "Windy station ID is not provided. Resending is disabled for now. Reconfigure your integration."
            )
            return False

        if not (windy_station_pw := checked_or(self.config.options.get(WINDY_STATION_PW), str, "")):
            _LOGGER.error("Windy station password is missing! Check your configuration.")
            self.last_status = "config_error"
            await self._disable_windy(
                "Windy password is not provided. Resending is disabled for now. Reconfigure your integration."
            )
            return False

        if self.log:
            _LOGGER.info(
                "Windy last update = %s, next update at: %s",
                str(self.last_update),
                str(self.next_update),
            )

        if self.next_update > dt_util.utcnow():
            self.last_status = "rate_limited_local"
            return False

        # Reserve the next send window now (before the await below) so a concurrent
        # webhook does not also pass the rate-limit check and double-send.
        self.next_update = dt_util.utcnow() + timed(minutes=5)

        # Convert *before* purging. PURGE_DATA lists PWS field names, so a reading that
        # only becomes a purge target after conversion - Ecowitt `tempinf` ->
        # `indoortempf`, WSLink `t1solrad` -> `solarradiation` - would otherwise slip
        # through to Windy unnoticed.
        converted = self._to_pws(data.copy(), source)
        purged_data = {key: value for key, value in converted.items() if key not in PURGE_DATA}

        request_url = f"{WINDY_URL}"

        purged_data["id"] = windy_station_id

        purged_data["time"] = "now"

        headers = {"Authorization": f"Bearer {windy_station_pw}"}

        if self.log:
            # Mask the station id (a credential) before logging the dataset.
            _LOGGER.info("Dataset for windy: %s", {**purged_data, "id": "***"})
        session = async_get_clientsession(self.hass)
        try:
            # Home Assistant's shared session sets no timeout, so without an explicit
            # one a stalled Windy would hold the station's webhook open for aiohttp's
            # 5 minute default and the TimeoutError branch below could never run in
            # time to answer the station.
            async with session.get(
                request_url,
                params=purged_data,
                headers=headers,
                timeout=ClientTimeout(total=FORWARD_TIMEOUT),
            ) as resp:
                try:
                    self.verify_windy_response(response=resp)
                except WindyNotInserted:
                    self.last_status = "not_inserted"
                    self.last_error = WINDY_NOT_INSERTED
                    self.invalid_response_count += 1

                    # log despite of settings
                    _LOGGER.error(
                        "%s Max retries before disable resend function: %s",
                        WINDY_NOT_INSERTED,
                        (WINDY_MAX_RETRIES - self.invalid_response_count),
                    )

                except WindyPasswordMissing:
                    # log despite of settings
                    self.last_status = "auth_error"
                    self.last_error = WINDY_INVALID_KEY
                    _LOGGER.critical(WINDY_INVALID_KEY)
                    await self._disable_windy(
                        reason="Windy password is missing in payload or Authorization header. Resending is disabled for now. Reconfigure your Windy settings."
                    )
                except WindyDuplicatePayloadDetected:
                    self.last_status = "duplicate"
                    self.last_error = "Duplicate payload detected by Windy server."
                    _LOGGER.critical(
                        "Duplicate payload detected by Windy server. Will try again later. Max retries before disabling resend function: %s",
                        (WINDY_MAX_RETRIES - self.invalid_response_count),
                    )
                    self.invalid_response_count += 1
                except WindyRateLimitExceeded:
                    # log despite of settings
                    self.last_status = "rate_limited_remote"
                    self.last_error = "Windy rate limit exceeded."
                    _LOGGER.critical(
                        "Windy responded with WindyRateLimitExceeded, this should happend only on restarting Home Assistant when we lost track of last send time. Pause resend for next 5 minutes."
                    )
                    self.next_update = dt_util.utcnow() + timedelta(minutes=5)

                except WindySuccess:
                    # reset invalid_response_count
                    self.invalid_response_count = 0
                    self.last_status = "ok"
                    self.last_error = None
                    if self.log:
                        _LOGGER.info(WINDY_SUCCESS)
                else:
                    self.last_status = "unexpected_response"
                    self.last_error = "Unexpected response from Windy."
                    # Always count unexpected responses toward the disable threshold,
                    # regardless of the logging setting.
                    self.invalid_response_count += 1
                    if self.log:
                        _LOGGER.debug(
                            "Unexpected response from Windy. Max retries before disabling resend function: %s",
                            (WINDY_MAX_RETRIES - self.invalid_response_count),
                        )
                finally:
                    if self.invalid_response_count >= WINDY_MAX_RETRIES:
                        _LOGGER.critical(
                            "Invalid response from Windy %s times. Disabling resend option.",
                            WINDY_MAX_RETRIES,
                        )
                        await self._disable_windy(
                            reason=f"Unable to send data to Windy ({WINDY_MAX_RETRIES} times). Disabling resend option for now. Please check your Windy configuration and enable this feature afterwards."
                        )

        # TimeoutError is not a ClientError: an `async_timeout`/`asyncio` timeout would
        # otherwise escape into the webhook handler and answer the station with HTTP 500,
        # even though the measured data was already stored.
        except (ClientError, TimeoutError) as ex:
            self.last_status = "client_error"
            # Store only the exception class - last_error is surfaced via entity
            # attributes; str(ex) could embed the request URL.
            self.last_error = type(ex).__name__
            _LOGGER.critical(
                "Invalid response from Windy: %s. Will try again later, max retries before disabling resend function: %s",
                str(ex),
                (WINDY_MAX_RETRIES - self.invalid_response_count),
            )
            self.invalid_response_count += 1
            if self.invalid_response_count >= WINDY_MAX_RETRIES:
                _LOGGER.critical(WINDY_UNEXPECTED)
                await self._disable_windy(
                    reason=f"Invalid response from Windy {WINDY_MAX_RETRIES} times. Disabling resending option."
                )
        self.last_update = dt_util.utcnow()
        self.next_update = self.last_update + timed(minutes=5)

        if self.log:
            _LOGGER.info("Next update: %s", str(self.next_update))

        return True
