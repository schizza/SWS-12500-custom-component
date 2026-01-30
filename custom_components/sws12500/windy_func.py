"""Windy functions."""

from datetime import datetime, timedelta
import logging

from aiohttp.client_exceptions import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    PURGE_DATA,
    WINDY_ENABLED,
    WINDY_INVALID_KEY,
    WINDY_LOGGER_ENABLED,
    WINDY_NOT_INSERTED,
    WINDY_STATION_ID,
    WINDY_STATION_PW,
    WINDY_SUCCESS,
    WINDY_UNEXPECTED,
    WINDY_URL,
)
from .utils import update_options

_LOGGER = logging.getLogger(__name__)

RESPONSE_FOR_TEST = False


class WindyNotInserted(Exception):
    """NotInserted state."""


class WindySuccess(Exception):
    """WindySucces state."""


class WindyApiKeyError(Exception):
    """Windy API Key error."""


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
        self.last_update = datetime.now()
        self.next_update = datetime.now() + timed(minutes=1)

        self.log = self.config.options.get(WINDY_LOGGER_ENABLED)
        self.invalid_response_count = 0

    def verify_windy_response(  # pylint: disable=useless-return
        self,
        response: str,
    ) -> WindyNotInserted | WindySuccess | WindyApiKeyError | None:
        """Verify answer form Windy."""

        if self.log:
            _LOGGER.info("Windy response raw response: %s", response)

        if "NOTICE" in response:
            raise WindyNotInserted

        if "SUCCESS" in response:
            raise WindySuccess

        if "Invalid API key" in response:
            raise WindyApiKeyError

        if "Unauthorized" in response:
            raise WindyApiKeyError

        return None

    async def push_data_to_windy(self, data, wslink: bool = False):
        """Pushes weather data do Windy stations.

        Interval is 5 minutes, otherwise Windy would not accepts data.

        we are sending almost the same data as we received
        from station. But we need to do some clean up.
        """

        text_for_test = None

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
                purged_data.pop(purge)

        if wslink:
            # WSLink -> Windy params
            if "t1ws" in purged_data:
                purged_data["wind"] = purged_data.pop("t1ws")
            if "t1wgust" in purged_data:
                purged_data["gust"] = purged_data.pop("t1wgust")
            if "t1wdir" in purged_data:
                purged_data["winddir"] = purged_data.pop("t1wdir")
            if "t1hum" in purged_data:
                purged_data["humidity"] = purged_data.pop("t1hum")
            if "t1dew" in purged_data:
                purged_data["dewpoint"] = purged_data.pop("t1dew")
            if "t1tem" in purged_data:
                purged_data["temp"] = purged_data.pop("t1tem")
            if "rbar" in purged_data:
                purged_data["mbar"] = purged_data.pop("rbar")
            if "t1rainhr" in purged_data:
                purged_data["precip"] = purged_data.pop("t1rainhr")
            if "t1uvi" in purged_data:
                purged_data["uv"] = purged_data.pop("t1uvi")
            if "t1solrad" in purged_data:
                purged_data["solarradiation"] = purged_data.pop("t1solrad")

        windy_station_id = self.config.options.get(WINDY_STATION_ID)
        windy_station_pw = self.config.options.get(WINDY_STATION_PW)

        request_url = f"{WINDY_URL}"

        purged_data["id"] = windy_station_id
        purged_data["time"] = "now"

        headers = {"Authorization": f"Bearer {windy_station_pw}"}

        if self.log:
            _LOGGER.info("Dataset for windy: %s", purged_data)
        session = async_get_clientsession(self.hass, verify_ssl=False)
        try:
            async with session.get(
                request_url, params=purged_data, headers=headers
            ) as resp:
                status = await resp.text()
                try:
                    self.verify_windy_response(status)
                except WindyNotInserted:
                    # log despite of settings
                    _LOGGER.error(WINDY_NOT_INSERTED)

                    text_for_test = WINDY_NOT_INSERTED

                except WindyApiKeyError:
                    # log despite of settings
                    _LOGGER.critical(WINDY_INVALID_KEY)
                    text_for_test = WINDY_INVALID_KEY

                    await update_options(self.hass, self.config, WINDY_ENABLED, False)

                except WindySuccess:
                    if self.log:
                        _LOGGER.info(WINDY_SUCCESS)
                    text_for_test = WINDY_SUCCESS

        except ClientError as ex:
            _LOGGER.critical("Invalid response from Windy: %s", str(ex))
            self.invalid_response_count += 1
            if self.invalid_response_count > 3:
                _LOGGER.critical(WINDY_UNEXPECTED)
                text_for_test = WINDY_UNEXPECTED
                await update_options(self.hass, self.config, WINDY_ENABLED, False)

        self.last_update = datetime.now()
        self.next_update = self.last_update + timed(minutes=5)

        if self.log:
            _LOGGER.info("Next update: %s", str(self.next_update))

        if RESPONSE_FOR_TEST and text_for_test:
            return text_for_test
        return None
