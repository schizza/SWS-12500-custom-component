from custom_components.sws12500.data import (
    ENTRY_ADD_ENTITIES,
    ENTRY_COORDINATOR,
    ENTRY_DESCRIPTIONS,
    ENTRY_LAST_OPTIONS,
)


def test_data_constants():
    assert ENTRY_COORDINATOR == "coordinator"
    assert ENTRY_ADD_ENTITIES == "async_add_entities"
    assert ENTRY_DESCRIPTIONS == "sensor_descriptions"
    assert ENTRY_LAST_OPTIONS == "last_options"
