"""Heat / wind-chill indices must work on WSLink too.

`_auto_enable_derived_sensors` creates both entities as soon as temperature and
humidity (resp. wind speed) arrive, but the WSLink descriptions only ever read the
station's own ``t1heat`` / ``t1chill``. A station that does not report those left both
entities Unavailable forever, while the WU/PWS platform computed them.

The payload is metric, the NWS formulas are Fahrenheit-based (and mph for wind chill),
and the WSLink entities are declared in Celsius - so the conversions matter as much as
the fallback itself.
"""

from __future__ import annotations

import pytest

from custom_components.sws12500.const import (
    CHILL_INDEX,
    HEAT_INDEX,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    WIND_SPEED,
)
from custom_components.sws12500.sensors_wslink import SENSOR_TYPES_WSLINK
from custom_components.sws12500.utils import (
    celsius_to_fahrenheit,
    chill_index,
    fahrenheit_to_celsius,
    heat_index,
    wslink_chill_index,
    wslink_heat_index,
)

# The remapped form of a real payload from a station that sends neither t1heat nor
# t1chill (t1tem/t1hum/t1ws in metric units).
LIVE_PAYLOAD: dict[str, str] = {
    OUTSIDE_TEMP: "6.2",
    OUTSIDE_HUMIDITY: "40",
    WIND_SPEED: "30.6",
}


def _description(key: str):
    return next(desc for desc in SENSOR_TYPES_WSLINK if desc.key == key)


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


def test_indices_are_computed_when_the_station_omits_them() -> None:
    """The reported bug: both entities stayed empty for this exact payload."""
    assert wslink_heat_index(LIVE_PAYLOAD) is not None
    assert wslink_chill_index(LIVE_PAYLOAD) is not None


def test_computed_values_are_celsius_and_plausible() -> None:
    """6.2 C at 40% RH with strong wind: heat index near ambient, chill below it."""
    heat = wslink_heat_index(LIVE_PAYLOAD)
    chill = wslink_chill_index(LIVE_PAYLOAD)
    assert heat is not None and chill is not None

    # Sanity-check the magnitude - a Fahrenheit result leaking through would be ~39/28.
    assert -10 < heat < 15, heat
    assert -10 < chill < 15, chill
    # Wind chill must be colder than the still-air temperature at 30.6 m/s.
    assert chill < 6.2


def test_wind_is_converted_to_mph() -> None:
    """`chill_index` converts temperature but not wind, and its formula needs mph.

    Feeding m/s straight in understates the wind and yields a warmer chill.
    """
    correct = wslink_chill_index(LIVE_PAYLOAD)

    naive_f = chill_index(
        {OUTSIDE_TEMP: celsius_to_fahrenheit(6.2), WIND_SPEED: 30.6},  # m/s, unconverted
    )
    assert naive_f is not None
    naive = round(fahrenheit_to_celsius(naive_f), 2)

    assert correct is not None
    assert correct < naive, f"unconverted wind gives {naive}, converted gives {correct}"


# ---------------------------------------------------------------------------
# The station's own reading still wins
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fn", "key"),
    [(wslink_heat_index, HEAT_INDEX), (wslink_chill_index, CHILL_INDEX)],
    ids=["heat", "chill"],
)
def test_station_reported_value_takes_precedence(fn, key) -> None:
    """t1heat / t1chill are already Celsius and must be passed through untouched."""
    assert fn({**LIVE_PAYLOAD, key: "3.5"}) == 3.5


@pytest.mark.parametrize(
    ("fn", "key"),
    [(wslink_heat_index, HEAT_INDEX), (wslink_chill_index, CHILL_INDEX)],
    ids=["heat", "chill"],
)
def test_empty_reported_value_falls_back_to_computing(fn, key) -> None:
    """The station sends "" for absent fields; that must not shadow the fallback."""
    assert fn({**LIVE_PAYLOAD, key: ""}) is not None


# ---------------------------------------------------------------------------
# Missing inputs stay quiet
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", [OUTSIDE_TEMP, OUTSIDE_HUMIDITY])
def test_heat_index_needs_temp_and_humidity(missing) -> None:
    payload = {k: v for k, v in LIVE_PAYLOAD.items() if k != missing}
    assert wslink_heat_index(payload) is None


@pytest.mark.parametrize("missing", [OUTSIDE_TEMP, WIND_SPEED])
def test_chill_index_needs_temp_and_wind(missing) -> None:
    payload = {k: v for k, v in LIVE_PAYLOAD.items() if k != missing}
    assert wslink_chill_index(payload) is None


def test_no_inputs_at_all_is_none() -> None:
    assert wslink_heat_index({}) is None
    assert wslink_chill_index({}) is None


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("key", "expected"), [(HEAT_INDEX, wslink_heat_index), (CHILL_INDEX, wslink_chill_index)])
def test_descriptions_use_the_wslink_helpers(key, expected) -> None:
    """`value_from_data_fn` wins in WeatherSensor.native_value, so it must be set."""
    desc = _description(key)
    assert desc.value_from_data_fn is expected


def test_wu_platform_still_computes_in_fahrenheit() -> None:
    """The WU descriptions are Fahrenheit-native; they must keep the raw helpers."""
    from custom_components.sws12500.sensors_weather import SENSOR_TYPES_WEATHER_API

    by_key = {d.key: d for d in SENSOR_TYPES_WEATHER_API}
    assert by_key[HEAT_INDEX].value_from_data_fn is heat_index
    assert by_key[CHILL_INDEX].value_from_data_fn is chill_index
