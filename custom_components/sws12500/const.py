"""Constants."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

# Integration specific constants.
DOMAIN = "sws12500"
DEV_DBG: Final = "dev_debug_checkbox"


# Common constants
API_KEY = "API_KEY"
API_ID = "API_ID"

SENSORS_TO_LOAD: Final = "sensors_to_load"

# Option key holding the raw `t234cXtp` probe types last reported by the station.
# Persisted rather than kept in runtime state because the channel humidity entities
# are created during entry setup, before any payload arrives.
CHANNEL_TYPES: Final = "channel_types"

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
HCHO: Final = "hcho"
VOC: Final = "voc"
T9_BATTERY: Final = "t9_battery"  # T9 sensors are HCHO and VOC
T9_CONN: Final = "t9_conn"

# --- Base console (WSLink API v0.6, no sensor type) -------------------------
ABS_PRESSURE: Final = "abs_pressure"  # abar

# --- Type1 outdoor ----------------------------------------------------------
FEELS_LIKE: Final = "feels_like"  # t1feels
WIND_SPEED_AVG10: Final = "wind_speed_avg10"  # t1ws10mav

# --- Type5 lightning --------------------------------------------------------
# `t5lst` is an integer the API documents only as "Last Lightning strike time";
# it is not an epoch (the vendor example shows 9999), so it is treated as minutes
# elapsed, with 9999 as the "no strike recorded" sentinel - see `lightning_minutes`.
LIGHTNING_LAST: Final = "lightning_last"  # t5lst
LIGHTNING_DISTANCE: Final = "lightning_distance"  # t5lskm
# The API lists both `t5lsf` ("strike count last 1 Hours") and `t5ls1htc` ("count
# total of during 1 Hour"). They overlap; both are exposed rather than guessing
# which one a given firmware populates.
LIGHTNING_STRIKES_1H: Final = "lightning_strikes_1h"  # t5lsf
LIGHTNING_COUNT_5M: Final = "lightning_count_5m"  # t5ls5mtc
LIGHTNING_COUNT_30M: Final = "lightning_count_30m"  # t5ls30mtc
LIGHTNING_COUNT_1H: Final = "lightning_count_1h"  # t5ls1htc
LIGHTNING_COUNT_1D: Final = "lightning_count_1d"  # t5ls1dtc
LIGHTNING_BATTERY: Final = "lightning_battery"  # t5lsbat (0/1)

# --- Type6 water leak, CH1-7 ------------------------------------------------
# Numbered as the API does (CH1-7). The temp/humidity channels use a legacy
# off-by-one (integration CH2 == WSLink CH1); that quirk is not repeated here.
LEAK_CH: Final[tuple[str, ...]] = tuple(f"leak_ch{ch}" for ch in range(1, 8))
LEAK_CH_BATTERY: Final[tuple[str, ...]] = tuple(f"leak_ch{ch}_battery" for ch in range(1, 8))

# --- Type8 particulate matter ----------------------------------------------
PM25: Final = "pm25"  # t8pm25
PM10: Final = "pm10"  # t8pm10
PM25_AQI: Final = "pm25_aqi"  # t8pm25ai
PM10_AQI: Final = "pm10_aqi"  # t8pm10ai
T8_BATTERY: Final = "t8_battery"  # t8bat (0-5)

# --- Type10 CO2 -------------------------------------------------------------
CO2: Final = "co2"  # t10co2
T10_BATTERY: Final = "t10_battery"  # t10bat (0-5)

# --- Type11 CO --------------------------------------------------------------
CO: Final = "co"  # t11co
T11_BATTERY: Final = "t11_battery"  # t11bat (0-5)


# Health specific constants
HEALTH_URL = "/station/health"


# PWS specific constants
DEFAULT_URL = "/weatherstation/updateweatherstation.php"

PURGE_DATA: Final = [
    "ID",
    "PASSWORD",
    "wsid",
    "wspw",
    "passkey",
    "PASSKEY",
    "action",
    "rtfreq",
    "realtime",
    "dateutc",
    "solarradiation",
    "indoortempf",
    "indoorhumidity",
    "dailyrainin",
]

"""NOTE: These are sensors that should be available with PWS protocol according to https://support.weather.com/s/article/PWS-Upload-Protocol?language=en_US:

I have no option to test, if it will work correctly. So their implementation will be in future releases.

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
# Failed sends in a row before resending is disabled. Timeouts are excluded on purpose -
# a slow upstream is transient, see the TimeoutError branch in `PocasiPush`.
POCASI_CZ_MAX_RETRIES: Final = 3

# Pocasi Meteo accepts Ecowitt only as a POST in the Ecowitt protocol itself - the
# station payload is forwarded verbatim rather than translated to PWS. Per their
# integration notes the account credentials go in the query string, and the password
# parameter is `PAS` (not `PASS` / `PASSWORD` as on the PWS endpoint):
#   ms.pocasimeteo.cz/ws_ecowitt/ws.php?ID=xxxx&PAS=yyyy
POCASI_CZ_ECOWITT_URL: Final = "/ws_ecowitt/ws.php"
POCASI_CZ_ECOWITT_ID_PARAM: Final = "ID"
POCASI_CZ_ECOWITT_PW_PARAM: Final = "PAS"


WSLINK: Final = "wslink"
LEGACY_ENABLED: Final = "legacy_enabled"

WINDY_MAX_RETRIES: Final = 3
WSLINK_ADDON_PORT: Final = "WSLINK_ADDON_PORT"

# Forwarding to Windy / Pocasi Meteo is awaited inline in the station's own request
# path, so an upstream that accepts the connection and never answers would hold the
# webhook open. aiohttp's default is a 5 minute total, long past the point where the
# station itself gives up; cut the send short instead and retry on the next push.
FORWARD_TIMEOUT: Final = 15  # seconds

ECOWITT: Final = "ecowitt"
ECOWITT_WEBHOOK_ID: Final = "ecowitt_webhook_id"
ECOWITT_ENABLED: Final = "ecowitt_enabled"
ECOWITT_URL_PREFIX: Final = "/weatherhub"

# Ecowitt field names -> the field names Windy accepts.
#
# Windy has no Ecowitt endpoint, so an Ecowitt payload has to be translated before it
# can be forwarded there. The target vocabulary is mostly the PWS/WU one Windy already
# receives from a real PWS station, but not exactly: Windy documents the UV index as
# lowercase `uv` (https://stations.windy.com/api-reference) while WU spells it `UV`
# (see REMAP_ITEMS). This table follows Windy, which is its only consumer.
#
# Deliberately an allowlist, not a "strip the bad keys" denylist: the Ecowitt payload
# also carries device metadata (stationtype, model, freq, runtime, heap, interval) that
# is meaningless upstream, and a denylist would forward whatever fields a future
# firmware adds.
#
# This is the *full* mapping, not the set of fields that end up on the wire: five of
# the entries below (`dateutc`, `solarradiation`, `dailyrainin`, `indoortempf`,
# `indoorhumidity`) are in PURGE_DATA and are stripped by `push_data_to_windy` right
# after the conversion. They are listed so the translation itself stays complete and
# keeps working if the purge list ever changes.
#
# Multi-channel temp/humidity (temp1f..temp7f) are intentionally absent - the PWS
# protocol has no equivalent, and mapping them onto its soil fields would send wrong
# data.
REMAP_ECOWITT_TO_WINDY: Final[dict[str, str]] = {
    # same name on both sides, listed so the allowlist is complete
    "tempf": "tempf",
    "humidity": "humidity",
    "windspeedmph": "windspeedmph",
    "windgustmph": "windgustmph",
    "winddir": "winddir",
    "dailyrainin": "dailyrainin",
    "solarradiation": "solarradiation",
    "dateutc": "dateutc",
    "uv": "uv",
    # renamed between the two protocols
    "dewpointf": "dewptf",
    "baromrelin": "baromin",
    "tempinf": "indoortempf",
    "humidityin": "indoorhumidity",
    "hourlyrainin": "rainin",  # WU `rainin` is the accumulation over the past hour
}

REMAP_ECOWITT_COMPAT: dict[str, str] = {
    "tempf": OUTSIDE_TEMP,
    "humidity": OUTSIDE_HUMIDITY,
    "dewpointf": DEW_POINT,
    "windspeedmph": WIND_SPEED,
    "windgustmph": WIND_GUST,
    "winddir": WIND_DIR,
    "dailyrainin": DAILY_RAIN,
    "solarradiation": SOLAR_RADIATION,
    "tempinf": INDOOR_TEMP,
    "humidityin": INDOOR_HUMIDITY,
    "uv": UV,
    "baromrelin": BARO_PRESSURE,
    "temp1f": CH2_TEMP,
    "humidity1": CH2_HUMIDITY,
    "temp2f": CH3_TEMP,
    "humidity2": CH3_HUMIDITY,
    "temp3f": CH4_TEMP,
    "humidity3": CH4_HUMIDITY,
    "temp4f": CH5_TEMP,
    "humidity4": CH5_HUMIDITY,
    "temp5f": CH6_TEMP,
    "humidity5": CH6_HUMIDITY,
    "temp6f": CH7_TEMP,
    "humidity6": CH7_HUMIDITY,
    "temp7f": CH8_TEMP,
    "humidity7": CH8_HUMIDITY,
}

POCASI_CZ_API_KEY = "POCASI_CZ_API_KEY"
POCASI_CZ_API_ID = "POCASI_CZ_API_ID"
POCASI_CZ_SEND_INTERVAL = "POCASI_SEND_INTERVAL"
POCASI_CZ_ENABLED = "pocasi_enabled_checkbox"
# Misspelled key used by config entries created before version 2 (see `async_migrate_entry`).
POCASI_CZ_ENABLED_LEGACY: Final = "pocasi_enabled_chcekbox"
POCASI_CZ_LOGGER_ENABLED = "pocasi_logger_checkbox"
POCASI_INVALID_KEY: Final = "Pocasi Meteo refused to accept data. Invalid ID/Key combination?"
POCASI_CZ_SUCCESS: Final = "Successfully sent data to Pocasi Meteo"
POCASI_CZ_UNEXPECTED: Final = (
    f"Pocasi Meteo responded unexpectedly {POCASI_CZ_MAX_RETRIES} times in row. Resending is now disabled!"
)

WINDY_STATION_ID = "WINDY_STATION_ID"
WINDY_STATION_PW = "WINDY_STATION_PWD"
WINDY_ENABLED: Final = "windy_enabled_checkbox"
WINDY_LOGGER_ENABLED: Final = "windy_logger_checkbox"
WINDY_NOT_INSERTED: Final = "Windy responded with 400 error. Invalid ID/password combination?"
WINDY_INVALID_KEY: Final = (
    "Windy API KEY is invalid. Send data to Windy is now disabled. Check your API KEY and try again."
)
WINDY_SUCCESS: Final = "Windy successfully sent data and data was successfully inserted by Windy API"
WINDY_UNEXPECTED: Final = (
    f"Windy responded unexpectedly {WINDY_MAX_RETRIES} times in a row. Send to Windy is now disabled!"
)



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
    # NOTE: connection flags (t1cn / t234cXcn / t9cn) are intentionally NOT remapped.
    # They are used only as gating inputs (see CONNECTION_GATED_SENSORS), which read the
    # raw payload keys. Remapping them used to leak ghost "*_connection" keys (with no
    # entity) into the coordinator data and into persisted SENSORS_TO_LOAD.
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
    "t9hcho": HCHO,
    "t9voclv": VOC,
    "t9bat": T9_BATTERY,  # T9 battery is 0-5, where 5 is full
    # --- base console -----------------------------------------------------
    "abar": ABS_PRESSURE,
    # --- Type1 outdoor ----------------------------------------------------
    "t1feels": FEELS_LIKE,
    "t1ws10mav": WIND_SPEED_AVG10,
    # --- Type5 lightning --------------------------------------------------
    "t5lst": LIGHTNING_LAST,
    "t5lskm": LIGHTNING_DISTANCE,
    "t5lsf": LIGHTNING_STRIKES_1H,
    "t5ls5mtc": LIGHTNING_COUNT_5M,
    "t5ls30mtc": LIGHTNING_COUNT_30M,
    "t5ls1htc": LIGHTNING_COUNT_1H,
    "t5ls1dtc": LIGHTNING_COUNT_1D,
    "t5lsbat": LIGHTNING_BATTERY,
    # --- Type6 water leak CH1-7 -------------------------------------------
    **{f"t6c{ch}wls": LEAK_CH[ch - 1] for ch in range(1, 8)},
    **{f"t6c{ch}bat": LEAK_CH_BATTERY[ch - 1] for ch in range(1, 8)},
    # --- Type8 particulate matter -----------------------------------------
    "t8pm25": PM25,
    "t8pm10": PM10,
    "t8pm25ai": PM25_AQI,
    "t8pm10ai": PM10_AQI,
    "t8bat": T8_BATTERY,
    # --- Type10 CO2 -------------------------------------------------------
    "t10co2": CO2,
    "t10bat": T10_BATTERY,
    # --- Type11 CO --------------------------------------------------------
    "t11co": CO,
    "t11bat": T11_BATTERY,
}

# NOTE: Add more sensors
#
# 'inbat'  indoor battery level (1 normal, 0 low)
# 't1bat': outdoor battery level (1 normal, 0 low)
# 't234c1bat': CH2 battery level (1 normal, 0 low)  CH2 in integration is CH1 in WSLink
#
# In the following there are sensors that should be available by WSLink.
# We need to compare them to PWS API to make sure, we have the same internal
# representation of same sensors.

### WSLink API v0.6 coverage
#
# Every upload parameter the API document defines is now handled: base console,
# Type1 outdoor, Type2/3/4 channels, Type5 lightning, Type6 water leak, Type8
# particulate matter, Type9 HCHO/VOC, Type10 CO2 and Type11 CO.
#
# `tests/test_wslink_api_coverage.py` pins that list, so a parameter cannot be
# dropped by a refactor and a future API revision fails the suite until its new
# parameters are mapped here.
#
# Two are handled with a documented caveat, because the API does not define them:
#   - `inbat` is the only battery with no stated scale; it is read as 0/1 like the
#     other wireless probes (see BATTERY_LIST).
#   - `t5lst` has no unit and the vendor example uses 9999; it is read as minutes
#     elapsed with 9999 meaning "nothing recorded" (see `lightning_minutes`).


# How the station reports each battery decides which entity it becomes. The two tuples
# below are the single source of truth for that split - `battery_sensors_def` generates
# both entity description sets from them, so a key cannot end up with two entities.
#
# They must stay disjoint, and every `*_BATTERY` constant must appear in exactly one of
# them; `tests/test_battery_classification.py` enforces both, and
# `tests/test_wslink_api_coverage.py` additionally pins each battery to the wording of
# the API document. That matters because getting it wrong is silent: a 0-5 battery read
# as a 0/1 flag reports "not low" for every level above empty, discarding most of the
# reading. The API annotates the difference explicitly - "(Normal=1, Low battery=0)"
# versus "(0~5) remark: 5 is full" - so a new battery only has to be read carefully.

# Reported as 0/1 (low/normal) -> BinarySensorDeviceClass.BATTERY.
BATTERY_LIST: Final[tuple[str, ...]] = (
    OUTSIDE_BATTERY,
    INDOOR_BATTERY,
    CH2_BATTERY,
    CH3_BATTERY,
    CH4_BATTERY,
    CH5_BATTERY,
    CH6_BATTERY,
    CH7_BATTERY,
    CH8_BATTERY,
    LIGHTNING_BATTERY,
    *LEAK_CH_BATTERY,
)

# Reported as a 0-5 level, 5 being full -> percentage SensorDeviceClass.BATTERY.
BATTERY_NON_BINARY: Final[tuple[str, ...]] = (T8_BATTERY, T9_BATTERY, T10_BATTERY, T11_BATTERY)


# Which raw `t234cXtp` parameter describes the probe behind each channel humidity
# reading. The API's compatible-sensor list maps the value to a probe kind:
#   2 = thermo-hygrometer, 3 = pool sensor, 4 = soil moisture & temperature
# A soil probe reports soil moisture, not air humidity, which is a different Home
# Assistant device class - see `channel_humidity_device_class`.
CH_HUMIDITY_TYPE_PARAM: Final[dict[str, str]] = {
    CH2_HUMIDITY: "t234c1tp",
    CH3_HUMIDITY: "t234c2tp",
    CH4_HUMIDITY: "t234c3tp",
    CH5_HUMIDITY: "t234c4tp",
    CH6_HUMIDITY: "t234c5tp",
    CH7_HUMIDITY: "t234c6tp",
    CH8_HUMIDITY: "t234c7tp",
}

# `t234cXtp` value for a soil moisture & temperature probe.
CH_TYPE_SOIL: Final = 4


CONNECTION_GATED_SENSORS: Final[dict[str, list[str]]] = {
    # Main outdoor probe (Type1). A payload that omits `t1cn` is not gated at all -
    # see `remap_wslink_items` - so this cannot blank a station that never reports it.
    "t1cn": [
        OUTSIDE_TEMP,
        OUTSIDE_HUMIDITY,
        FEELS_LIKE,
        CHILL_INDEX,
        HEAT_INDEX,
        DEW_POINT,
        WIND_DIR,
        WIND_SPEED,
        WIND_SPEED_AVG10,
        WIND_GUST,
        RAIN,
        HOURLY_RAIN,
        DAILY_RAIN,
        WEEKLY_RAIN,
        MONTHLY_RAIN,
        YEARLY_RAIN,
        UV,
        SOLAR_RADIATION,
        WBGT_TEMP,
        OUTSIDE_BATTERY,
    ],
    # Multi-channel temp/humidity probes (CH2 - CH8)
    "t234c1cn": [CH2_TEMP, CH2_HUMIDITY, CH2_BATTERY],
    "t234c2cn": [CH3_TEMP, CH3_HUMIDITY, CH3_BATTERY],
    "t234c3cn": [CH4_TEMP, CH4_HUMIDITY, CH4_BATTERY],
    "t234c4cn": [CH5_TEMP, CH5_HUMIDITY, CH5_BATTERY],
    "t234c5cn": [CH6_TEMP, CH6_HUMIDITY, CH6_BATTERY],
    "t234c6cn": [CH7_TEMP, CH7_HUMIDITY, CH7_BATTERY],
    "t234c7cn": [CH8_TEMP, CH8_HUMIDITY, CH8_BATTERY],
    # T9 HCHO/VOC probe
    "t9cn": [HCHO, VOC, T9_BATTERY],
    # Lightning probe
    "t5lscn": [
        LIGHTNING_LAST,
        LIGHTNING_DISTANCE,
        LIGHTNING_STRIKES_1H,
        LIGHTNING_COUNT_5M,
        LIGHTNING_COUNT_30M,
        LIGHTNING_COUNT_1H,
        LIGHTNING_COUNT_1D,
        LIGHTNING_BATTERY,
    ],
    # Water leak probes CH1-7
    **{f"t6c{ch}cn": [LEAK_CH[ch - 1], LEAK_CH_BATTERY[ch - 1]] for ch in range(1, 8)},
    # Particulate matter probe
    "t8cn": [PM25, PM10, PM25_AQI, PM10_AQI, T8_BATTERY],
    # CO2 probe
    "t10cn": [CO2, T10_BATTERY],
    # CO probe
    "t11cn": [CO, T11_BATTERY],
}


class VOCLevel(StrEnum):
    """WSLink VOC Level 1-5 (1-worst)."""

    UNHEALTHY = "unhealthy"
    POOR = "poor"
    MODERATE = "moderate"
    GOOD = "good"
    EXCELLENT = "excellent"


VOC_LEVEL_MAP: dict[int, VOCLevel] = {
    1: VOCLevel.UNHEALTHY,
    2: VOCLevel.POOR,
    3: VOCLevel.MODERATE,
    4: VOCLevel.GOOD,
    5: VOCLevel.EXCELLENT,
}


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

