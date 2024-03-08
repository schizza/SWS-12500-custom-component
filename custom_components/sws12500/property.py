 @property
    def translation_key(self):
        """Return translation key."""
        return self.entity_description.translation_key

    @property
    def device_class(self):
        """Return device class."""
        return self.entity_description.device_class

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return str(self.entity_description.name)

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self.entity_description.key

    @property
    def native_value(self):
        """Return value of entity."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon of entity."""
        return str(self.entity_description.icon)

    @property
    def native_unit_of_measurement(self) -> str:
        """Return unit of measurement."""
        return str(self.entity_description.native_unit_of_measurement)

    @property
    def state_class(self) -> str:
        """Return stateClass."""

        return str(self.entity_description.state_class)

    @property
    def suggested_unit_of_measurement(self) -> str:
        """Return sugestet_unit_of_measurement."""
        return str(self.entity_description.suggested_unit_of_measurement)
    