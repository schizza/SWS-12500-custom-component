from custom_components.sws12500.const import DEFAULT_URL, DOMAIN, WINDY_URL, WSLINK_URL


def test_const_values():
    assert DOMAIN == "sws12500"
    assert DEFAULT_URL == "/weatherstation/updateweatherstation.php"
    assert WSLINK_URL == "/data/upload.php"
    assert WINDY_URL == "https://stations.windy.com/api/v2/observation/update"
