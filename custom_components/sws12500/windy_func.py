"""Windy functions."""

from datetime import datetime, timedelta
import logging

from aiohttp.client import ClientResponse
from aiohttp.client_exceptions import ClientError
from py_typecheck import checked

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
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
from .utils import update_options

_LOGGER = logging.getLogger(__name__)


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

        """ lets wait for 1 minute to get initial data from station
            and then try to push first data to Windy
        """
        self.last_update: datetime = datetime.now()
        self.next_update: datetime = datetime.now() + timed(minutes=1)

        self.log: bool = self.config.options.get(WINDY_LOGGER_ENABLED, False)

        # Lets chcek if Windy server is responding right.
        # Otherwise, try 3 times and then disable resending.
        self.invalid_response_count: int = 0

    # Refactored responses verification.
    #
    # We now comply to API at https://stations.windy.com/api-reference
    def verify_windy_response(self, response: ClientResponse):
        """Verify answer form Windy."""

        if self.log and response:
            _LOGGER.info("Windy raw response: %s", response.text)

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

        return indata

    async def _disable_windy(self, reason: str) -> None:
        """Disable Windy resending."""

        if not await update_options(self.hass, self.config, WINDY_ENABLED, False):
            _LOGGER.debug("Failed to set Windy options to false.")

        persistent_notification.create(self.hass, reason, "Windy resending disabled.")

    async def push_data_to_windy(
        self, data: dict[str, str], wslink: bool = False
    ) -> bool:
        """Pushes weather data do Windy stations.

        Interval is 5 minutes, otherwise Windy would not accepts data.

        we are sending almost the same data as we received
        from station. But we need to do some clean up.
        """

        # First check if we have valid credentials, before any data manipulation.
        if (
            windy_station_id := checked(self.config.options.get(WINDY_STATION_ID), str)
        ) is None:
            _LOGGER.error("Windy API key is not provided! Check your configuration.")
            await self._disable_windy(
                "Windy API key is not provided. Resending is disabled for now. Reconfigure your integration."
            )
            return False

        if (
            windy_station_pw := checked(self.config.options.get(WINDY_STATION_PW), str)
        ) is None:
            _LOGGER.error(
                "Windy station password is missing! Check your configuration."
            )
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

        if self.next_update > datetime.now():
            return False

        purged_data = data.copy()

        for purge in PURGE_DATA:
            if purge in purged_data:
                _ = purged_data.pop(purge)

        if wslink:
            # WSLink -> Windy params
            purged_data = self._covert_wslink_to_pws(purged_data)

        request_url = f"{WINDY_URL}"

        purged_data["id"] = windy_station_id

        purged_data["time"] = "now"

        headers = {"Authorization": f"Bearer {windy_station_pw}"}

        if self.log:
            _LOGGER.info("Dataset for windy: %s", purged_data)
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                request_url, params=purged_data, headers=headers
            ) as resp:
                try:
                    self.verify_windy_response(response=resp)
                except WindyNotInserted:
                    # log despite of settings
                    _LOGGER.error(WINDY_NOT_INSERTED)
                    self.invalid_response_count += 1

                except WindyPasswordMissing:
                    # log despite of settings
                    _LOGGER.critical(WINDY_INVALID_KEY)
                    await self._disable_windy(
                        reason="Windy password is missing in payload or Authorization header. Resending is disabled for now. Reconfigure your Windy settings."
                    )
                except WindyDuplicatePayloadDetected:
                    _LOGGER.critical(
                        "Duplicate payload detected by Windy server. Will try again later. Max retries before disabling resend function: %s",
                        (WINDY_MAX_RETRIES - self.invalid_response_count),
                    )
                    self.invalid_response_count += 1

                except WindySuccess:
                    if self.log:
                        _LOGGER.info(WINDY_SUCCESS)
                else:
                    if self.log:
                        _LOGGER.debug(WINDY_NOT_INSERTED)

        except ClientError as ex:
            _LOGGER.critical(
                "Invalid response from Windy: %s. Will try again later, max retries before disabling resend function: %s",
                str(ex),
                (WINDY_MAX_RETRIES - self.invalid_response_count),
            )
            self.invalid_response_count += 1
            if self.invalid_response_count >= WINDY_MAX_RETRIES:
                _LOGGER.critical(WINDY_UNEXPECTED)
                await self._disable_windy(
                    reason="Invalid response from Windy 3 times. Disabling resending option."
                )
        self.last_update = datetime.now()
        self.next_update = self.last_update + timed(minutes=5)

        if self.log:
            _LOGGER.info("Next update: %s", str(self.next_update))

        return True
