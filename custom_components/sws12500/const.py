"""Constants."""

from enum import StrEnum
from typing import Final

DOMAIN = "sws12500"
DEFAULT_URL = "/weatherstation/updateweatherstation.php"
WINDY_URL = "https://stations.windy.com/pws/update/"

ICON = "mdi:weather"

API_KEY = "API_KEY"
API_ID = "API_ID"

SENSORS_TO_LOAD: Final = "sensors_to_load"

DEV_DBG: Final = "dev_debug_checkbox"

WINDY_API_KEY = "WINDY_API_KEY"
WINDY_ENABLED: Final = "windy_enabled_checkbox"
WINDY_LOGGER_ENABLED: Final = "windy_logger_checkbox"
WINDY_NOT_INSERTED: Final = "Data was succefuly sent to Windy, but not inserted by Windy API. Does anyone else sent data to Windy?"
WINDY_INVALID_KEY: Final = "Windy API KEY is invalid. Send data to Windy is now disabled. Check your API KEY and try again."
WINDY_SUCCESS: Final = (
    "Windy successfully sent data and data was successfully inserted by Windy API"
)
WINDY_UNEXPECTED: Final = (
    "Windy responded unexpectedly 3 times in a row. Send to Windy is now disabled!"
)

INVALID_CREDENTIALS: Final = [
    "API",
    "API_ID",
    "API ID",
    "_ID",
    "ID",
    "API KEY",
    "API_KEY",
    "KEY",
    "_KEY",
]

PURGE_DATA: Final = [
    "ID",
    "PASSWORD",
    "action",
    "rtfreq",
    "realtime",
    "dateutc",
    "solarradiation",
    "indoortempf",
    "indoorhumidity",
    "dailyrainin",
]

BARO_PRESSURE: Final = "baro_pressure"
OUTSIDE_TEMP: Final = "outside_temp"
DEW_POINT: Final = "dew_point"
OUTSIDE_HUMIDITY: Final = "outside_humidity"
WIND_SPEED: Final = "wind_speed"
WIND_GUST: Final = "wind_gust"
WIND_DIR: Final = "wind_dir"
WIND_AZIMUT: Final = "wind_azimut"
RAIN: Final = "rain"
DAILY_RAIN: Final = "daily_rain"
SOLAR_RADIATION: Final = "solar_radiation"
INDOOR_TEMP: Final = "indoor_temp"
INDOOR_HUMIDITY: Final = "indoor_humidity"
UV: Final = "uv"
CH2_TEMP: Final = "ch2_temp"
CH2_HUMIDITY: Final = "ch2_humidity"
CH3_TEMP: Final = "ch3_temp"
CH3_HUMIDITY: Final = "ch3_humidity"
CH4_TEMP: Final = "ch4_temp"
CH4_HUMIDITY: Final = "ch4_humidity"
HEAT_INDEX: Final = "heat_index"
CHILL_INDEX: Final = "chill_index"


REMAP_ITEMS: dict = {
    "baromin": BARO_PRESSURE,
    "tempf": OUTSIDE_TEMP,
    "dewptf": DEW_POINT,
    "humidity": OUTSIDE_HUMIDITY,
    "windspeedmph": WIND_SPEED,
    "windgustmph": WIND_GUST,
    "winddir": WIND_DIR,
    "rainin": RAIN,
    "dailyrainin": DAILY_RAIN,
    "solarradiation": SOLAR_RADIATION,
    "indoortempf": INDOOR_TEMP,
    "indoorhumidity": INDOOR_HUMIDITY,
    "UV": UV,
    "soiltempf": CH2_TEMP,
    "soilmoisture": CH2_HUMIDITY,
    "soiltemp2f": CH3_TEMP,
    "soilmoisture2": CH3_HUMIDITY,
    "soiltemp3f": CH4_TEMP,
    "soilmoisture3": CH4_HUMIDITY,
}

DISABLED_BY_DEFAULT: Final = [
    CH2_TEMP,
    CH2_HUMIDITY,
    CH3_TEMP,
    CH3_HUMIDITY,
    CH4_TEMP,
    CH4_HUMIDITY,
]


class UnitOfDir(StrEnum):
    """Wind direrction azimut."""

    NNE = "nne"
    NE = "ne"
    ENE = "ene"
    E = "e"
    ESE = "ese"
    SE = "se"
    SSE = "sse"
    S = "s"
    SSW = "ssw"
    SW = "sw"
    WSW = "wsw"
    W = "w"
    WNW = "wnw"
    NW = "nw"
    NNW = "nnw"
    N = "n"


AZIMUT: list[UnitOfDir] = [
    UnitOfDir.NNE,
    UnitOfDir.NE,
    UnitOfDir.ENE,
    UnitOfDir.E,
    UnitOfDir.ESE,
    UnitOfDir.SE,
    UnitOfDir.SSE,
    UnitOfDir.S,
    UnitOfDir.SSW,
    UnitOfDir.SW,
    UnitOfDir.WSW,
    UnitOfDir.W,
    UnitOfDir.WNW,
    UnitOfDir.NW,
    UnitOfDir.NNW,
    UnitOfDir.N,
]
