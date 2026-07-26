from custom_components.sws12500.utils import celsius_to_fahrenheit, fahrenheit_to_celsius


def test_temperature_conversion():
    assert celsius_to_fahrenheit(0) == 32
    assert celsius_to_fahrenheit(100) == 212
    assert fahrenheit_to_celsius(32) == 0
    assert fahrenheit_to_celsius(212) == 100
