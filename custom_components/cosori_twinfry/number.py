"""Staged temperature and time per zone.

These numbers are the settings the next start of that zone sends. They are
not the fryer's live values (those are the sensors), and changing them never
changes or restarts a running cook: the TF101S API has no command for that.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant

from .const import PROGRAM_MAX_MINUTES
from .entity import TwinFryEntity

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import TwinFryConfigEntry, TwinFryData

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TwinFryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the numbers."""
    data = entry.runtime_data
    async_add_entities(
        entity
        for zone in (1, 2)
        for entity in (TemperatureSetting(data, zone), TimeSetting(data, zone))
    )


class _SettingNumber(TwinFryEntity, NumberEntity):
    """Common behaviour of the staged settings."""

    _attr_mode = NumberMode.BOX

    async def async_added_to_hass(self) -> None:
        """Follow the controller."""
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        """Local settings are always editable."""
        return True


class TemperatureSetting(_SettingNumber):
    """Temperature for the next start of a zone."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_translation_key = "zone_temperature"

    def __init__(self, data: TwinFryData, zone: int) -> None:
        """Initialise the number."""
        super().__init__(data, "temperature", zone)

    @property
    def native_unit_of_measurement(self) -> str:
        """Unit of the fryer."""
        if self.coordinator.device.temp_unit.code == "f":
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def native_min_value(self) -> float:
        """Lowest temperature of the staged program."""
        return self.controller.temperature_limits(self.zone)[0]

    @property
    def native_max_value(self) -> float:
        """Highest temperature of the staged program."""
        return self.controller.temperature_limits(self.zone)[1]

    @property
    def native_step(self) -> float:
        """Step of the staged program."""
        return self.controller.temperature_limits(self.zone)[2]

    @property
    def native_value(self) -> float:
        """Staged temperature."""
        return self.controller.settings[self.zone].temperature

    async def async_set_native_value(self, value: float) -> None:
        """Stage a temperature."""
        self.controller.async_set_temperature(self.zone, value)


class TimeSetting(_SettingNumber):
    """Cook time for the next start of a zone."""

    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 1
    _attr_native_step = 1
    _attr_translation_key = "zone_time"

    def __init__(self, data: TwinFryData, zone: int) -> None:
        """Initialise the number."""
        super().__init__(data, "time", zone)

    @property
    def native_max_value(self) -> float:
        """Longest time the integration accepts for the staged program."""
        return PROGRAM_MAX_MINUTES[self.controller.settings[self.zone].program]

    @property
    def native_value(self) -> float:
        """Staged minutes."""
        return self.controller.settings[self.zone].minutes

    async def async_set_native_value(self, value: float) -> None:
        """Stage a cook time."""
        self.controller.async_set_minutes(self.zone, value)
