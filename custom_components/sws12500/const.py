"""Constants."""

from enum import StrEnum
from typing import Final

DOMAIN = "sws12500"
DEFAULT_URL = "/weatherstation/updateweatherstation.php"
WSLINK_URL = "/data/upload.php"
WINDY_URL = "https://stations.windy.com/pws/update/"
DATABASE_PATH = "/config/home-assistant_v2.db"

POCASI_CZ_URL: Final = "http://ms.pocasimeteo.cz"
POCASI_CZ_SEND_MINIMUM: Final = 12  # minimal time to resend data


ICON = "mdi:weather"

API_KEY = "API_KEY"
API_ID = "API_ID"

SENSORS_TO_LOAD: Final = "sensors_to_load"
SENSOR_TO_MIGRATE: Final = "sensor_to_migrate"

DEV_DBG: Final = "dev_debug_checkbox"
WSLINK: Final = "wslink"

ECOWITT: Final = "ecowitt"
ECOWITT_WEBHOOK_ID: Final = "ecowitt_webhook_id"
ECOWITT_ENABLED: Final = "ecowitt_enabled"

POCASI_CZ_API_KEY = "POCASI_CZ_API_KEY"
POCASI_CZ_API_ID = "POCASI_CZ_API_ID"
POCASI_CZ_SEND_INTERVAL = "POCASI_SEND_INTERVAL"
POCASI_CZ_ENABLED = "pocasi_enabled_chcekbox"
POCASI_CZ_LOGGER_ENABLED = "pocasi_logger_checkbox"
POCASI_INVALID_KEY: Final = (
    "Pocasi Meteo refused to accept data. Invalid ID/Key combination?"
)
POCASI_CZ_SUCCESS: Final = "Successfully sent data to Pocasi Meteo"
POCASI_CZ_UNEXPECTED: Final = (
    "Pocasti Meteo responded unexpectedly 3 times in row. Resendig is now disabled!"
)

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

PURGE_DATA_POCAS: Final = [
    "ID",
    "PASSWORD",
    "action",
    "rtfreq",
]


BARO_PRESSURE: Final = "baro_pressure"
OUTSIDE_TEMP: Final = "outside_temp"
DEW_POINT: Final = "dew_point"
OUTSIDE_HUMIDITY: Final = "outside_humidity"
OUTSIDE_CONNECTION: Final = "outside_connection"
OUTSIDE_BATTERY: Final = "outside_battery"
WIND_SPEED: Final = "wind_speed"
WIND_GUST: Final = "wind_gust"
WIND_DIR: Final = "wind_dir"
WIND_AZIMUT: Final = "wind_azimut"
RAIN: Final = "rain"
HOURLY_RAIN: Final = "hourly_rain"
WEEKLY_RAIN: Final = "weekly_rain"
MONTHLY_RAIN: Final = "monthly_rain"
YEARLY_RAIN: Final = "yearly_rain"
DAILY_RAIN: Final = "daily_rain"
SOLAR_RADIATION: Final = "solar_radiation"
INDOOR_TEMP: Final = "indoor_temp"
INDOOR_HUMIDITY: Final = "indoor_humidity"
INDOOR_BATTERY: Final = "indoor_battery"
UV: Final = "uv"
CH2_TEMP: Final = "ch2_temp"
CH2_HUMIDITY: Final = "ch2_humidity"
CH2_CONNECTION: Final = "ch2_connection"
CH2_BATTERY: Final = "ch2_battery"
CH3_TEMP: Final = "ch3_temp"
CH3_HUMIDITY: Final = "ch3_humidity"
CH3_CONNECTION: Final = "ch3_connection"
CH4_TEMP: Final = "ch4_temp"
CH4_HUMIDITY: Final = "ch4_humidity"
CH4_CONNECTION: Final = "ch4_connection"
HEAT_INDEX: Final = "heat_index"
CHILL_INDEX: Final = "chill_index"
WBGT_TEMP: Final = "wbgt_temp"


REMAP_ITEMS: dict[str, str] = {
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

REMAP_WSLINK_ITEMS: dict[str, str] = {
    "intem": INDOOR_TEMP,
    "inhum": INDOOR_HUMIDITY,
    "t1tem": OUTSIDE_TEMP,
    "t1hum": OUTSIDE_HUMIDITY,
    "t1dew": DEW_POINT,
    "t1wdir": WIND_DIR,
    "t1ws": WIND_SPEED,
    "t1wgust": WIND_GUST,
    "t1rainra": RAIN,
    "t1raindy": DAILY_RAIN,
    "t1solrad": SOLAR_RADIATION,
    "rbar": BARO_PRESSURE,
    "t1uvi": UV,
    "t234c1tem": CH2_TEMP,
    "t234c1hum": CH2_HUMIDITY,
    "t1cn": OUTSIDE_CONNECTION,
    "t234c1cn": CH2_CONNECTION,
    "t234c2cn": CH3_CONNECTION,
    "t1chill": CHILL_INDEX,
    "t1heat": HEAT_INDEX,
    "t1rainhr": HOURLY_RAIN,
    "t1rainwy": WEEKLY_RAIN,
    "t1rainmth": MONTHLY_RAIN,
    "t1rainyr": YEARLY_RAIN,
    "t234c2tem": CH3_TEMP,
    "t234c2hum": CH3_HUMIDITY,
    "t1bat": OUTSIDE_BATTERY,
    "inbat": INDOOR_BATTERY,
    "t234c1bat": CH2_BATTERY,
    "t1wbgt": WBGT_TEMP,
}

# TODO: Add more sensors
#
# 'inbat'  indoor battery level (1 normal, 0 low)
# 't1bat': outdoor battery level (1 normal, 0 low)
# 't234c1bat': CH2 battery level (1 normal, 0 low)  CH2 in integration is CH1 in WSLink


DISABLED_BY_DEFAULT: Final = [
    CH2_TEMP,
    CH2_HUMIDITY,
    CH2_BATTERY,
    CH3_TEMP,
    CH3_HUMIDITY,
    CH4_TEMP,
    CH4_HUMIDITY,
    OUTSIDE_BATTERY,
    WBGT_TEMP,
]

BATTERY_LIST = [
    OUTSIDE_BATTERY,
    INDOOR_BATTERY,
    CH2_BATTERY,
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


class UnitOfBat(StrEnum):
    """Battery level unit of measure."""

    LOW = "low"
    NORMAL = "normal"
    UNKNOWN = "drained"


BATTERY_LEVEL: list[UnitOfBat] = [
    UnitOfBat.LOW,
    UnitOfBat.NORMAL,
    UnitOfBat.UNKNOWN,
]
