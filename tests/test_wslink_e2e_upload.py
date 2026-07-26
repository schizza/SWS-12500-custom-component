"""End-to-end proof that a full WSLink v0.6 upload becomes Home Assistant entities.

Every other WSLink test in this suite inspects tables or drives the coordinator with a
request stub. This one is the user's view: a real Home Assistant instance with the
integration set up, a real HTTP request to `/data/upload.php` carrying all 107 upload
parameters from API.pdf v0.6, and then the entity registry / state machine as the
frontend would show them - name, state, unit, device class, state class.

It exists so the three things that fail silently can be seen rather than reasoned about:

- a 0-5 battery published as `%` instead of a "low battery" flag (and the reverse),
- a leak sensor whose `1` means wet while its battery's `0` means low,
- a soil probe on a channel reporting soil moisture rather than air humidity.

Set ``SWS_E2E_REPORT`` to a file path to also dump the resulting entity table there.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sws12500.const import (
    API_ID,
    API_KEY,
    CHANNEL_TYPES,
    DOMAIN,
    WIND_GUST,
    WIND_SPEED,
    WIND_SPEED_AVG10,
    WSLINK,
    WSLINK_URL,
)
from custom_components.sws12500.sensors_wslink import SENSOR_TYPES_WSLINK
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    STATE_OFF,
    STATE_ON,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

# Credentials, timestamp and API version are not readings.
ENVELOPE = ("wsid", "wspw", "datetime", "apiver")

STATION_ID = "e2e-station"
STATION_PW = "e2e-secret"

# A complete WSLink v0.6 upload. Values are plausible readings, chosen so that a
# mis-classification is visible in the rendered state rather than hidden by a
# coincidence: every level battery is 3 (of 5) and every binary battery is 0 (low),
# so a swapped convention shows up as "60 %" where "on/low" belongs, or vice versa.
FULL_PAYLOAD: dict[str, str] = {
    # --- credentials / envelope -------------------------------------------
    "wsid": STATION_ID,
    "wspw": STATION_PW,
    "datetime": "2026-07-26 12:00:00",
    "apiver": "0.6",
    # --- base console ------------------------------------------------------
    "rbar": "1013.2",
    "abar": "998.7",
    "intem": "22.4",
    "inhum": "45",
    "inbat": "1",
    # --- Type1 outdoor -----------------------------------------------------
    "t1tem": "18.6",
    "t1hum": "62",
    "t1feels": "17.9",
    "t1chill": "18.1",
    "t1heat": "18.9",
    "t1dew": "11.2",
    "t1wdir": "225",
    "t1ws": "3.4",
    "t1ws10mav": "2.8",
    "t1wgust": "7.1",
    "t1rainra": "0.4",
    "t1rainhr": "1.2",
    "t1raindy": "5.6",
    "t1rainwy": "12.8",
    "t1rainmth": "44.2",
    "t1rainyr": "512.9",
    "t1uvi": "4",
    "t1solrad": "612.5",
    "t1wbgt": "21.3",
    "t1bat": "0",  # (Normal=1, Low battery=0) -> low
    "t1cn": "1",
    # --- Type2/3/4 channels CH1-CH7 (CH1 is the integration's CH2) ---------
    # Channel 3 (integration CH4) carries a soil probe (tp=4).
    **{
        k: v
        for ch in range(1, 8)
        for k, v in {
            f"t234c{ch}tem": f"{15 + ch}.5",
            f"t234c{ch}hum": f"{50 + ch}",
            f"t234c{ch}bat": "0",  # (Normal=1, Low battery=0) -> low
            f"t234c{ch}cn": "1",
            f"t234c{ch}tp": "4" if ch == 3 else "2",
        }.items()
    },
    # --- Type5 lightning ---------------------------------------------------
    "t5lst": "17",
    "t5lskm": "12",
    "t5lsf": "3",
    "t5ls5mtc": "1",
    "t5ls30mtc": "2",
    "t5ls1htc": "3",
    "t5ls1dtc": "9",
    "t5lsbat": "0",  # (Normal=1, Low battery=0) -> low
    "t5lscn": "1",
    # --- Type6 water leak CH1-CH7 -----------------------------------------
    # CH2 is wet (wls=1); every leak battery is low (bat=0) - opposite conventions
    # inside one family.
    **{
        k: v
        for ch in range(1, 8)
        for k, v in {
            f"t6c{ch}wls": "1" if ch == 2 else "0",
            f"t6c{ch}bat": "0",
            f"t6c{ch}cn": "1",
        }.items()
    },
    # --- Type8 particulate matter -----------------------------------------
    "t8pm25": "12",
    "t8pm10": "21",
    "t8pm25ai": "51",
    "t8pm10ai": "34",
    "t8bat": "3",  # (0~5) remark: 5 is full -> 60 %
    "t8cn": "1",
    # --- Type9 HCHO / VOC --------------------------------------------------
    "t9hcho": "18",
    "t9voclv": "4",
    "t9bat": "3",
    "t9cn": "1",
    # --- Type10 CO2 --------------------------------------------------------
    "t10co2": "812",
    "t10bat": "3",
    "t10cn": "1",
    # --- Type11 CO ---------------------------------------------------------
    "t11co": "6",
    "t11bat": "3",
    "t11cn": "1",
}


async def _setup_wslink_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Set up the integration exactly as a configured WSLink installation."""
    assert await async_setup_component(hass, "http", {"http": {}})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sencor SWS 12500",
        data={},
        options={
            API_ID: STATION_ID,
            API_KEY: STATION_PW,
            WSLINK: True,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_table(hass: HomeAssistant, entity_reg: er.EntityRegistry) -> list[dict[str, str]]:
    """Render every entity of the integration the way the frontend shows it."""
    rows: list[dict[str, str]] = []
    for reg_entry in er.async_entries_for_config_entry(
        entity_reg, next(iter(hass.config_entries.async_entries(DOMAIN))).entry_id
    ):
        state = hass.states.get(reg_entry.entity_id)
        if state is None:
            continue
        rows.append(
            {
                "entity_id": reg_entry.entity_id,
                "name": str(state.attributes.get("friendly_name", "")),
                "state": state.state,
                "unit": str(state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or ""),
                "device_class": str(state.attributes.get(ATTR_DEVICE_CLASS) or ""),
                "state_class": str(state.attributes.get("state_class") or ""),
            }
        )
    return sorted(rows, key=lambda row: row["entity_id"])


def _row(rows: list[dict[str, str]], entity_id: str) -> dict[str, str]:
    """Return the rendered row for one entity, or fail listing what does exist."""
    for row in rows:
        if row["entity_id"] == entity_id:
            return row
    raise AssertionError(f"{entity_id} was never created; entities: {[r['entity_id'] for r in rows]}")


@pytest.fixture
async def wslink_report(
    hass: HomeAssistant,
    enable_custom_integrations,
    hass_client_no_auth,
    entity_registry: er.EntityRegistry,
):
    """Push the full API payload twice and return the resulting entity table.

    Twice on purpose: the first upload is auto-discovery (it creates the entities),
    the second is the steady state a running station produces, and it is the one whose
    values the entities must be showing.
    """
    await _setup_wslink_entry(hass)
    client = await hass_client_no_auth()

    for _ in range(2):
        response = await client.get(WSLINK_URL, params=FULL_PAYLOAD)
        assert response.status == 200
        assert await response.text() == "OK"
        await hass.async_block_till_done()

    return _entity_table(hass, entity_registry)


SENSOR = "sensor.weather_station_sws_12500_"
BINARY = "binary_sensor.weather_station_sws_12500_"


async def test_full_wslink_upload_creates_every_new_family(wslink_report) -> None:
    """A complete v0.6 upload must surface all the newly implemented families."""
    for entity_id in (
        # Type5 lightning
        SENSOR + "time_since_last_lightning_strike",
        SENSOR + "lightning_distance",
        SENSOR + "lightning_strikes_last_hour_t5lsf",
        SENSOR + "lightning_strikes_5_minutes",
        SENSOR + "lightning_strikes_30_minutes",
        SENSOR + "lightning_strike_total_1_hour_t5ls1htc",
        SENSOR + "lightning_strikes_1_day",
        BINARY + "lightning_sensor_battery",
        # Type8 particulate matter
        SENSOR + "pm2_5",
        SENSOR + "pm10",
        SENSOR + "pm2_5_aqi",
        SENSOR + "pm10_aqi",
        SENSOR + "pm_sensor_battery",
        # Type10 CO2 / Type11 CO
        SENSOR + "co2",
        SENSOR + "co2_sensor_battery",
        SENSOR + "co",
        SENSOR + "co_sensor_battery",
        # Parameters added to existing families
        SENSOR + "absolute_pressure",
        SENSOR + "feels_like",
        SENSOR + "wind_speed_10_min_average",
    ):
        _row(wslink_report, entity_id)

    # Type6 water leak: seven channels, each with its own battery.
    for ch in range(1, 8):
        _row(wslink_report, f"{BINARY}water_leak_ch{ch}")
        _row(wslink_report, f"{BINARY}water_leak_ch{ch}_battery")


async def test_device_classes_match_ha_documentation(wslink_report) -> None:
    """The classes the change verified against developers.home-assistant.io."""
    expected = {
        SENSOR + "pm2_5": SensorDeviceClass.PM25,
        SENSOR + "pm10": SensorDeviceClass.PM10,
        SENSOR + "pm2_5_aqi": SensorDeviceClass.AQI,
        SENSOR + "pm10_aqi": SensorDeviceClass.AQI,
        SENSOR + "co2": SensorDeviceClass.CO2,
        SENSOR + "co": SensorDeviceClass.CO,
        SENSOR + "lightning_distance": SensorDeviceClass.DISTANCE,
        SENSOR + "absolute_pressure": SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        SENSOR + "barometric_pressure": SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        SENSOR + "wind_speed_10_min_average": SensorDeviceClass.WIND_SPEED,
        SENSOR + "feels_like": SensorDeviceClass.TEMPERATURE,
        # HA documents no formaldehyde class, so HCHO keeps VOC-parts.
        SENSOR + "formaldehyde_hcho": SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS,
    }
    for entity_id, device_class in expected.items():
        row = _row(wslink_report, entity_id)
        assert row["device_class"] == device_class.value, row

    # AQI is unitless; the concentrations carry the units HA documents for their class.
    assert _row(wslink_report, SENSOR + "pm2_5_aqi")["unit"] == ""
    assert _row(wslink_report, SENSOR + "pm10_aqi")["unit"] == ""
    assert _row(wslink_report, SENSOR + "pm2_5")["unit"] == CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
    assert _row(wslink_report, SENSOR + "pm10")["unit"] == CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
    assert _row(wslink_report, SENSOR + "co2")["unit"] == CONCENTRATION_PARTS_PER_MILLION
    assert _row(wslink_report, SENSOR + "co")["unit"] == CONCENTRATION_PARTS_PER_MILLION
    assert _row(wslink_report, SENSOR + "lightning_distance")["unit"] == UnitOfLength.KILOMETERS
    assert _row(wslink_report, SENSOR + "absolute_pressure")["unit"] == UnitOfPressure.HPA


async def test_native_wind_speed_unit_is_metres_per_second() -> None:
    """The state renders in the user's unit system; the reading itself is m/s."""
    by_key = {desc.key: desc for desc in SENSOR_TYPES_WSLINK}
    for key in (WIND_SPEED, WIND_SPEED_AVG10, WIND_GUST):
        assert by_key[key].native_unit_of_measurement == UnitOfSpeed.METERS_PER_SECOND


async def test_batteries_use_the_convention_the_api_documents(wslink_report) -> None:
    """0/1 batteries stay flags; 0-5 batteries become percentages."""
    # Documented "(Normal=1, Low battery=0)". Sent as 0, so the flag reads "on" (low)
    # and carries no unit - a level battery misread as a flag would show "on" for 1-5.
    for entity_id in (
        BINARY + "outside_battery",
        BINARY + "lightning_sensor_battery",
        BINARY + "channel_2_battery",
        BINARY + "water_leak_ch1_battery",
    ):
        row = _row(wslink_report, entity_id)
        assert row["device_class"] == BinarySensorDeviceClass.BATTERY.value, row
        assert row["state"] == STATE_ON, f"{entity_id} should read as low battery: {row}"
        assert row["unit"] == "", f"{entity_id} must not carry a percentage unit: {row}"

    # inbat has no documented scale and is read as 0/1 (sent 1 = normal -> "off").
    console = _row(wslink_report, BINARY + "console_battery")
    assert console["device_class"] == BinarySensorDeviceClass.BATTERY.value, console
    assert console["state"] == STATE_OFF, console

    # Documented "(0~5) remark: 5 is full". Sent as 3, so 60 % - a flag misread as a
    # level would show "on"/"off" instead.
    for entity_id in (
        SENSOR + "pm_sensor_battery",
        SENSOR + "hcho_voc_sensor_battery",
        SENSOR + "co2_sensor_battery",
        SENSOR + "co_sensor_battery",
    ):
        row = _row(wslink_report, entity_id)
        assert row["device_class"] == SensorDeviceClass.BATTERY.value, row
        assert row["unit"] == PERCENTAGE, row
        assert row["state"] == "60", f"{entity_id} should render 3 of 5 as 60 %: {row}"


async def test_water_leak_and_its_battery_read_opposite_conventions(wslink_report) -> None:
    """Leak 1 = wet, battery 0 = low, in the same family and the same entity class."""
    wet = _row(wslink_report, BINARY + "water_leak_ch2")
    assert wet["device_class"] == BinarySensorDeviceClass.MOISTURE.value, wet
    assert wet["state"] == STATE_ON, f"t6c2wls=1 means wet: {wet}"

    dry = _row(wslink_report, BINARY + "water_leak_ch1")
    assert dry["device_class"] == BinarySensorDeviceClass.MOISTURE.value, dry
    assert dry["state"] == STATE_OFF, f"t6c1wls=0 means dry: {dry}"

    # Same payload digit, opposite meaning: the CH1 battery was sent 0 and is low.
    assert _row(wslink_report, BINARY + "water_leak_ch1_battery")["state"] == STATE_ON


async def test_soil_probe_channel_reports_moisture_not_humidity(wslink_report) -> None:
    """`t234c3tp=4` is a soil probe, so integration CH4 humidity is soil moisture."""
    soil = _row(wslink_report, SENSOR + "channel_4_humidity")
    assert soil["device_class"] == SensorDeviceClass.MOISTURE.value, soil

    air = _row(wslink_report, SENSOR + "channel_2_humidity")
    assert air["device_class"] == SensorDeviceClass.HUMIDITY.value, air


async def test_probe_types_are_persisted_so_the_class_survives_a_restart(
    hass: HomeAssistant, wslink_report, entity_registry: er.EntityRegistry
) -> None:
    """HA records the device class in the entity registry, so the type must persist.

    The types are stored in options rather than runtime state because entities are
    created during entry setup, before the first payload of the next run arrives.
    """
    entry = next(iter(hass.config_entries.async_entries(DOMAIN)))
    stored = entry.options.get(CHANNEL_TYPES, {})
    assert stored.get("t234c3tp") == "4", stored
    assert stored.get("t234c1tp") == "2", stored

    # Reload with no payload at all: the soil channel must still be soil moisture.
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    rows = _entity_table(hass, entity_registry)
    assert _row(rows, SENSOR + "channel_4_humidity")["device_class"] == SensorDeviceClass.MOISTURE.value
    assert _row(rows, SENSOR + "channel_2_humidity")["device_class"] == SensorDeviceClass.HUMIDITY.value


async def test_lightning_time_since_last_strike_reads_as_minutes(wslink_report) -> None:
    """`t5lst` has no documented unit; 17 is minutes and 9999 means "nothing recorded"."""
    row = _row(wslink_report, SENSOR + "time_since_last_lightning_strike")
    assert row["unit"] == UnitOfTime.MINUTES, row
    assert row["state"] == "17", row


async def test_t1cn_gating_drops_a_disconnected_probe_but_absence_does_not(
    hass: HomeAssistant,
    enable_custom_integrations,
    hass_client_no_auth,
    entity_registry: er.EntityRegistry,
) -> None:
    """The behavioural change existing installations feel.

    `t1cn=0` (explicitly disconnected) must stop publishing outdoor readings; a
    firmware that never sends `t1cn` says nothing, so its readings must be kept.
    """
    await _setup_wslink_entry(hass)
    client = await hass_client_no_auth()

    assert (await client.get(WSLINK_URL, params=FULL_PAYLOAD)).status == 200
    await hass.async_block_till_done()
    assert _row(_entity_table(hass, entity_registry), SENSOR + "outside_temperature")["state"] == "18.6"

    # Explicitly disconnected -> the stale reading must not be published.
    disconnected = {**FULL_PAYLOAD, "t1cn": "0", "t1tem": "99.9", "t1ws": "88.8"}
    assert (await client.get(WSLINK_URL, params=disconnected)).status == 200
    await hass.async_block_till_done()
    rows = _entity_table(hass, entity_registry)
    assert _row(rows, SENSOR + "outside_temperature")["state"] != "99.9"
    assert _row(rows, SENSOR + "wind_speed")["state"] != "88.8"

    # Firmware that omits t1cn gives no information -> keep the readings.
    absent = {k: v for k, v in FULL_PAYLOAD.items() if k != "t1cn"}
    absent["t1tem"] = "20.1"
    assert (await client.get(WSLINK_URL, params=absent)).status == 200
    await hass.async_block_till_done()
    assert _row(_entity_table(hass, entity_registry), SENSOR + "outside_temperature")["state"] == "20.1"


async def test_write_entity_report(wslink_report) -> None:
    """Dump the rendered entity table when SWS_E2E_REPORT names a file."""
    target = os.environ.get("SWS_E2E_REPORT")
    if not target:
        pytest.skip("SWS_E2E_REPORT not set")

    rows = wslink_report
    widths = {col: max(len(col), *(len(row[col]) for row in rows)) for col in rows[0]}
    header = " | ".join(col.ljust(widths[col]) for col in rows[0])
    lines = [
        f"WSLink API v0.6 - upload of all {len(FULL_PAYLOAD) - len(ENVELOPE)} parameters "
        f"(plus {len(ENVELOPE)} envelope fields) to {WSLINK_URL}",
        f"{len(rows)} entities created and populated in Home Assistant",
        "",
        header,
        "-+-".join("-" * widths[col] for col in rows[0]),
        *(" | ".join(row[col].ljust(widths[col]) for col in row) for row in rows),
    ]
    Path(target).write_text("\n".join(lines) + "\n", encoding="utf-8")
