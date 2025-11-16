"""Pocasi CZ resend functions."""

from datetime import datetime, timedelta
import logging
from typing import Any, Literal

from aiohttp import ClientError

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
from .utils import update_options

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

    async def push_data_to_server(
        self, data: dict[str, Any], mode: Literal["WU", "WSLINK"]
    ):
        """Pushes weather data to server."""

        _data = data.copy()
        _api_id = self.config.options.get(POCASI_CZ_API_ID)
        _api_key = self.config.options.get(POCASI_CZ_API_KEY)

        if self.log:
            _LOGGER.info(
                "Pocasi CZ last update = %s, next update at: %s",
                str(self.last_update),
                str(self.next_update),
            )

        if self.next_update > datetime.now():
            _LOGGER.debug(
                "Triggered update interval limit of %s seconds. Next possilbe update is set to: %s",
                self._interval,
                self.next_update,
            )
            return False

        request_url: str = ""
        if mode == "WSLINK":
            _data["wsid"] = _api_id
            _data["wspw"] = _api_key
            request_url = f"{POCASI_CZ_URL}{WSLINK_URL}"

        if mode == "WU":
            _data["ID"] = _api_id
            _data["PASSWORD"] = _api_key
            request_url = f"{POCASI_CZ_URL}{DEFAULT_URL}"

        session = async_get_clientsession(self.hass, verify_ssl=False)
        _LOGGER.debug(
            "Payload for Pocasi Meteo server: [mode=%s] [request_url=%s] = %s",
            mode,
            request_url,
            _data,
        )
        try:
            async with session.get(request_url, params=_data) as resp:
                status = await resp.text()
                try:
                    self.verify_response(status)

                except PocasiApiKeyError:
                    # log despite of settings
                    _LOGGER.critical(POCASI_INVALID_KEY)
                    await update_options(
                        self.hass, self.config, POCASI_CZ_ENABLED, False
                    )
                except PocasiSuccess:
                    if self.log:
                        _LOGGER.info(POCASI_CZ_SUCCESS)

        except ClientError as ex:
            _LOGGER.critical("Invalid response from Pocasi Meteo: %s", str(ex))
            self.invalid_response_count += 1
            if self.invalid_response_count > 3:
                _LOGGER.critical(POCASI_CZ_UNEXPECTED)
                await update_options(self.hass, self.config, POCASI_CZ_ENABLED, False)

        self.last_update = datetime.now()
        self.next_update = datetime.now() + timedelta(seconds=self._interval)

        if self.log:
            _LOGGER.info("Next update: %s", str(self.next_update))

        return None
