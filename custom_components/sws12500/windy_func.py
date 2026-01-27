"""Windy functions."""

from datetime import datetime, timedelta
import logging

from aiohttp.client_exceptions import ClientError
from py_typecheck.core import checked

from homeassistant.components import persistent_notification
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
        self.last_update: datetime = datetime.now()
        self.next_update: datetime = datetime.now() + timed(minutes=1)

        self.log: bool = self.config.options.get(WINDY_LOGGER_ENABLED, False)
        self.invalid_response_count: int = 0

    def verify_windy_response(
        self,
        response: str,
    ):
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

    async def push_data_to_windy(self, data: dict[str, str]) -> bool:
        """Pushes weather data do Windy stations.

        Interval is 5 minutes, otherwise Windy would not accepts data.

        we are sending almost the same data as we received
        from station. But we need to do some clean up.
        """

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

        if (
            windy_api_key := checked(self.config.options.get(WINDY_API_KEY), str)
        ) is None:
            _LOGGER.error("Windy API key is not provided! Check your configuration.")
            return False

        request_url = f"{WINDY_URL}{windy_api_key}"

        if self.log:
            _LOGGER.info("Dataset for windy: %s", purged_data)
        session = async_get_clientsession(self.hass, verify_ssl=False)
        try:
            async with session.get(request_url, params=purged_data, headers=headers) as resp:
                status = await resp.text()
                try:
                    self.verify_windy_response(status)
                except WindyNotInserted:
                    # log despite of settings
                    _LOGGER.error(WINDY_NOT_INSERTED)

                except WindyApiKeyError:
                    # log despite of settings
                    _LOGGER.critical(WINDY_INVALID_KEY)

                    if not (
                        await update_options(
                            self.hass, self.config, WINDY_ENABLED, False
                        )
                    ):
                        _LOGGER.debug("Failed to set Windy option to false.")

                except WindySuccess:
                    if self.log:
                        _LOGGER.info(WINDY_SUCCESS)
                else:
                    if self.log:
                        _LOGGER.debug(WINDY_NOT_INSERTED)

        except ClientError as ex:
            _LOGGER.critical("Invalid response from Windy: %s", str(ex))
            self.invalid_response_count += 1
            if self.invalid_response_count > 3:
                _LOGGER.critical(WINDY_UNEXPECTED)
                if not await update_options(
                    self.hass, self.config, WINDY_ENABLED, False
                ):
                    _LOGGER.debug("Failed to set Windy options to false.")

        self.last_update = datetime.now()
        self.next_update = self.last_update + timed(minutes=5)

        if self.log:
            _LOGGER.info("Next update: %s", str(self.next_update))

        return True
