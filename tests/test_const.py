from custom_components.sws12500.const import (
    DEFAULT_URL,
    DOMAIN,
    POCASI_CZ_MAX_RETRIES,
    POCASI_CZ_UNEXPECTED,
    WINDY_MAX_RETRIES,
    WINDY_UNEXPECTED,
    WINDY_URL,
    WSLINK_URL,
)


def test_const_values():
    assert DOMAIN == "sws12500"
    assert DEFAULT_URL == "/weatherstation/updateweatherstation.php"
    assert WSLINK_URL == "/data/upload.php"
    assert WINDY_URL == "https://stations.windy.com/api/v2/observation/update"


def test_retry_counts_in_user_facing_messages():
    """The retry count in the notification texts must follow the constants."""
    assert f"{WINDY_MAX_RETRIES} times" in WINDY_UNEXPECTED
    assert f"{POCASI_CZ_MAX_RETRIES} times" in POCASI_CZ_UNEXPECTED
