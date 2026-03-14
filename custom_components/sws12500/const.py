"""Constants."""

from enum import StrEnum
from typing import Final

# Integration specific constants.
DOMAIN = "sws12500"
DATABASE_PATH = "/config/home-assistant_v2.db"
ICON = "mdi:weather"
DEV_DBG: Final = "dev_debug_checkbox"


# Common constants
API_KEY = "API_KEY"
API_ID = "API_ID"

SENSORS_TO_LOAD: Final = "sensors_to_load"
SENSOR_TO_MIGRATE: Final = "sensor_to_migrate"

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


# Sensor constants
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
CH3_BATTERY: Final = "ch3_battery"
CH4_TEMP: Final = "ch4_temp"
CH4_HUMIDITY: Final = "ch4_humidity"
CH4_CONNECTION: Final = "ch4_connection"
CH4_BATTERY: Final = "ch4_battery"
CH5_TEMP: Final = "ch5_temp"
CH5_HUMIDITY: Final = "ch5_humidity"
CH5_CONNECTION: Final = "ch5_connection"
CH5_BATTERY: Final = "ch5_battery"
CH6_TEMP: Final = "ch6_temp"
CH6_HUMIDITY: Final = "ch6_humidity"
CH6_CONNECTION: Final = "ch6_connection"
CH6_BATTERY: Final = "ch6_battery"
CH7_TEMP: Final = "ch7_temp"
CH7_HUMIDITY: Final = "ch7_humidity"
CH7_CONNECTION: Final = "ch7_connection"
CH7_BATTERY: Final = "ch7_battery"
CH8_TEMP: Final = "ch8_temp"
CH8_HUMIDITY: Final = "ch8_humidity"
CH8_CONNECTION: Final = "ch8_connection"
CH8_BATTERY: Final = "ch8_battery"
HEAT_INDEX: Final = "heat_index"
CHILL_INDEX: Final = "chill_index"
WBGT_TEMP: Final = "wbgt_temp"


# Health specific constants
HEALTH_URL = "/station/health"


# PWS specific constants
DEFAULT_URL = "/weatherstation/updateweatherstation.php"

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
    "soiltemp4f": CH5_TEMP,
    "soilmoisture4": CH5_HUMIDITY,
    "soiltemp5f": CH6_TEMP,
    "soilmoisture5": CH6_HUMIDITY,
}


WSLINK_URL = "/data/upload.php"

WINDY_URL = "https://stations.windy.com/api/v2/observation/update"

POCASI_CZ_URL: Final = "http://ms.pocasimeteo.cz"
POCASI_CZ_SEND_MINIMUM: Final = 12  # minimal time to resend data


WSLINK: Final = "wslink"

WINDY_MAX_RETRIES: Final = 3

__all__ = [
    "DOMAIN",
    "DEFAULT_URL",
    "WSLINK_URL",
    "HEALTH_URL",
    "WINDY_URL",
    "DATABASE_PATH",
    "POCASI_CZ_URL",
    "POCASI_CZ_SEND_MINIMUM",
    "ICON",
    "API_KEY",
    "API_ID",
    "SENSORS_TO_LOAD",
    "SENSOR_TO_MIGRATE",
    "DEV_DBG",
    "WSLINK",
    "ECOWITT",
    "ECOWITT_WEBHOOK_ID",
    "ECOWITT_ENABLED",
    "POCASI_CZ_API_KEY",
    "POCASI_CZ_API_ID",
    "POCASI_CZ_SEND_INTERVAL",
    "POCASI_CZ_ENABLED",
    "POCASI_CZ_LOGGER_ENABLED",
    "POCASI_INVALID_KEY",
    "POCASI_CZ_SUCCESS",
    "POCASI_CZ_UNEXPECTED",
    "WINDY_STATION_ID",
    "WINDY_STATION_PW",
    "WINDY_ENABLED",
    "WINDY_LOGGER_ENABLED",
    "WINDY_NOT_INSERTED",
    "WINDY_INVALID_KEY",
    "WINDY_SUCCESS",
    "WINDY_UNEXPECTED",
    "INVALID_CREDENTIALS",
    "PURGE_DATA",
    "PURGE_DATA_POCAS",
    "BARO_PRESSURE",
    "OUTSIDE_TEMP",
    "DEW_POINT",
    "OUTSIDE_HUMIDITY",
    "OUTSIDE_CONNECTION",
    "OUTSIDE_BATTERY",
    "WIND_SPEED",
    "WIND_GUST",
    "WIND_DIR",
    "WIND_AZIMUT",
    "RAIN",
    "HOURLY_RAIN",
    "WEEKLY_RAIN",
    "MONTHLY_RAIN",
    "YEARLY_RAIN",
    "DAILY_RAIN",
    "SOLAR_RADIATION",
    "INDOOR_TEMP",
    "INDOOR_HUMIDITY",
    "INDOOR_BATTERY",
    "UV",
    "CH2_TEMP",
    "CH2_HUMIDITY",
    "CH2_CONNECTION",
    "CH2_BATTERY",
    "CH3_TEMP",
    "CH3_HUMIDITY",
    "CH3_CONNECTION",
    "CH4_TEMP",
    "CH4_HUMIDITY",
    "CH4_CONNECTION",
    "HEAT_INDEX",
    "CHILL_INDEX",
    "WBGT_TEMP",
    "REMAP_ITEMS",
    "REMAP_WSLINK_ITEMS",
    "DISABLED_BY_DEFAULT",
    "BATTERY_LIST",
    "UnitOfDir",
    "AZIMUT",
    "UnitOfBat",
    "BATTERY_LEVEL",
]

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

WINDY_STATION_ID = "WINDY_STATION_ID"
WINDY_STATION_PW = "WINDY_STATION_PWD"
WINDY_ENABLED: Final = "windy_enabled_checkbox"
WINDY_LOGGER_ENABLED: Final = "windy_logger_checkbox"
WINDY_NOT_INSERTED: Final = (
    "Windy responded with 400 error. Invalid ID/password combination?"
)
WINDY_INVALID_KEY: Final = "Windy API KEY is invalid. Send data to Windy is now disabled. Check your API KEY and try again."
WINDY_SUCCESS: Final = (
    "Windy successfully sent data and data was successfully inserted by Windy API"
)
WINDY_UNEXPECTED: Final = (
    "Windy responded unexpectedly 3 times in a row. Send to Windy is now disabled!"
)


PURGE_DATA_POCAS: Final = [
    "ID",
    "PASSWORD",
    "action",
    "rtfreq",
]


"""NOTE: These are sensors that should be available with PWS protocol acording to https://support.weather.com/s/article/PWS-Upload-Protocol?language=en_US:

I have no option to test, if it will work correctly. So their implementatnion will be in future releases.

leafwetness  - [%]
+ for sensor 2 use leafwetness2
visibility - [nm visibility]
pweather - [text] -- metar style (+RA)
clouds - [text] -- SKC, FEW, SCT, BKN, OVC
Pollution Fields:

AqNO - [ NO (nitric oxide) ppb ]
AqNO2T - (nitrogen dioxide), true measure ppb
AqNO2 - NO2 computed, NOx-NO ppb
AqNO2Y - NO2 computed, NOy-NO ppb
AqNOX - NOx (nitrogen oxides) - ppb
AqNOY - NOy (total reactive nitrogen) - ppb
AqNO3 - NO3 ion (nitrate, not adjusted for ammonium ion) UG/M3
AqSO4 - SO4 ion (sulfate, not adjusted for ammonium ion) UG/M3
AqSO2 - (sulfur dioxide), conventional ppb
AqSO2T - trace levels ppb
AqCO - CO (carbon monoxide), conventional ppm
AqCOT -CO trace levels ppb
AqEC - EC (elemental carbon) – PM2.5 UG/M3
AqOC - OC (organic carbon, not adjusted for oxygen and hydrogen) – PM2.5 UG/M3
AqBC - BC (black carbon at 880 nm) UG/M3
AqUV-AETH  - UV-AETH (second channel of Aethalometer at 370 nm) UG/M3
AqPM2.5 - PM2.5 mass - UG/M3
AqPM10 - PM10 mass - PM10 mass
AqOZONE - Ozone - ppb

"""

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
    "t234c3cn": CH4_CONNECTION,
    "t234c4cn": CH5_CONNECTION,
    "t234c5cn": CH6_CONNECTION,
    "t234c6cn": CH7_CONNECTION,
    "t234c7cn": CH8_CONNECTION,
    "t1chill": CHILL_INDEX,
    "t1heat": HEAT_INDEX,
    "t1rainhr": HOURLY_RAIN,
    "t1rainwy": WEEKLY_RAIN,
    "t1rainmth": MONTHLY_RAIN,
    "t1rainyr": YEARLY_RAIN,
    "t234c2tem": CH3_TEMP,
    "t234c2hum": CH3_HUMIDITY,
    "t234c3tem": CH4_TEMP,
    "t234c3hum": CH4_HUMIDITY,
    "t234c4tem": CH5_TEMP,
    "t234c4hum": CH5_HUMIDITY,
    "t234c5tem": CH6_TEMP,
    "t234c5hum": CH6_HUMIDITY,
    "t234c6tem": CH7_TEMP,
    "t234c6hum": CH7_HUMIDITY,
    "t234c7tem": CH8_TEMP,
    "t234c7hum": CH8_HUMIDITY,
    "t1bat": OUTSIDE_BATTERY,
    "inbat": INDOOR_BATTERY,
    "t234c1bat": CH2_BATTERY,
    "t234c2bat": CH3_BATTERY,
    "t234c3bat": CH4_BATTERY,
    "t234c4bat": CH5_BATTERY,
    "t234c5bat": CH6_BATTERY,
    "t234c6bat": CH7_BATTERY,
    "t234c7bat": CH8_BATTERY,
    "t1wbgt": WBGT_TEMP,
}

# NOTE: Add more sensors
#
# 'inbat'  indoor battery level (1 normal, 0 low)
# 't1bat': outdoor battery level (1 normal, 0 low)
# 't234c1bat': CH2 battery level (1 normal, 0 low)  CH2 in integration is CH1 in WSLin
#
# In the following there are sensors that should be available by WSLink.
# We need to compare them to PWS API to make sure, we have the same intarnal
# representation of same sensors.

### TODO: These are sensors, that should be supported in WSLink API according to their API documentation:
# &t5lst= Last Lightning strike time integer
# &t5lskm= Lightning distance integer km
# &t5lsf= Lightning strike count last 1 Hours integer
# &t5ls5mtc= Lightning count total of during 5 minutes integer
# &t5ls30mtc= Lightning count total of during 30 minutes integer
# &t5ls1htc= Lightning count total of during 1 Hour integer
# &t5ls1dtc= Lightning count total of during 1 day integer
# &t5lsbat= Lightning Sensor battery (Normal=1, Low battery=0) integer
# &t5lscn= Lightning Sensor connection (Connected=1, No connect=0) integer
# &t6c1wls= Water leak sensor CH1 (Leak=1, No leak=0) integer
# &t6c1bat= Water leak sensor CH1 battery (Normal=1, Low battery=0) integer
# &t6c1cn= Water leak sensor CH1 connection (Connected=1, No connect=0) integer
# &t6c2wls= Water leak sensor CH2 (Leak=1, No leak=0) integer
# &t6c2bat= Water leak sensor CH2 battery (Normal=1, Low battery=0) integer
# &t6c2cn= Water leak sensor CH2 connection (Connected=1, No connect=0) integer
# &t6c3wls= Water leak sensor CH3 (Leak=1, No leak=0) integer
# &t6c3bat= Water leak sensor CH3 battery (Normal=1, Low battery=0) integer
# &t6c3cn= Water leak sensor CH3 connection (Connected=1, No connect=0) integer
# &t6c4wls= Water leak sensor CH4 (Leak=1, No leak=0) integer
# &t6c4bat= Water leak sensor CH4 battery (Normal=1, Low battery=0) integer
# &t6c4cn= Water leak sensor CH4 connection (Connected=1, No connect=0) integer
# &t6c5wls= Water leak sensor CH5 (Leak=1, No leak=0) integer
# &t6c5bat= Water leak sensor CH5 battery (Normal=1, Low battery=0) integer
# &t6c5cn= Water leak sensor CH5 connection (Connected=1, No connect=0) integer
# &t6c6wls= Water leak sensor CH6 (Leak=1, No leak=0) integer
# &t6c6bat= Water leak sensor CH6 battery (Normal=1, Low battery=0) integer
# &t6c6cn= Water leak sensor CH6 connection (Connected=1, No connect=0) integer
# &t6c7wls= Water leak sensor CH7 (Leak=1, No leak=0) integer
# &t6c7bat= Water leak sensor CH7 battery (Normal=1, Low battery=0) integer
# &t6c7cn= Water leak sensor CH7 connection (Connected=1, No connect=0) integer
# &t8pm25= PM2.5 concentration integer ug/m3
# &t8pm10= PM10 concentration integer ug/m3
# &t8pm25ai= PM2.5 AQI integer
# &t8pm10ai = PM10 AQI integer
# &t8bat= PM sensor battery level (0~5) remark: 5 is full integer
# &t8cn= PM sensor connection (Connected=1, No connect=0) integer
# &t9hcho= HCHO concentration integer ppb
# &t9voclv= VOC level (1~5) 1 is the highest level, 5 is the lowest VOC level integer
# &t9bat= HCHO / VOC sensor battery level (0~5) remark: 5 is full integer
# &t9cn= HCHO / VOC sensor connection (Connected=1, No connect=0) integer
# &t10co2= CO2 concentration integer ppm
# &t10bat= CO2 sensor battery level (0~5) remark: 5 is full integer
# &t10cn= CO2 sensor connection (Connected=1, No connect=0) integer
# &t11co= CO concentration integer ppm
# &t11bat= CO sensor battery level (0~5) remark: 5 is full integer
# &t11cn= CO sensor connection (Connected=1, No connect=0) integer
#

DISABLED_BY_DEFAULT: Final = [
    CH2_TEMP,
    CH2_HUMIDITY,
    CH2_BATTERY,
    CH3_TEMP,
    CH3_HUMIDITY,
    CH3_BATTERY,
    CH4_TEMP,
    CH4_HUMIDITY,
    CH4_BATTERY,
    CH5_TEMP,
    CH5_HUMIDITY,
    CH5_BATTERY,
    CH6_TEMP,
    CH6_HUMIDITY,
    CH6_BATTERY,
    CH7_TEMP,
    CH7_HUMIDITY,
    CH7_BATTERY,
    CH8_TEMP,
    CH8_HUMIDITY,
    CH8_BATTERY,
    OUTSIDE_BATTERY,
    WBGT_TEMP,
]

BATTERY_LIST = [
    OUTSIDE_BATTERY,
    INDOOR_BATTERY,
    CH2_BATTERY,
    CH2_BATTERY,
    CH3_BATTERY,
    CH4_BATTERY,
    CH5_BATTERY,
    CH6_BATTERY,
    CH7_BATTERY,
    CH8_BATTERY,
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
