"""Binary sensors for the COSORI TwinFry integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

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
    """Set up the binary sensors."""
    data = entry.runtime_data
    async_add_entities([ZoneCookingSensor(data, 1), ZoneCookingSensor(data, 2), OnlineSensor(data)])


class ZoneCookingSensor(TwinFryEntity, BinarySensorEntity):
    """On while the zone is confirmed cooking."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_translation_key = "zone_cooking"

    def __init__(self, data: TwinFryData, zone: int) -> None:
        """Initialise the sensor."""
        super().__init__(data, "cooking", zone)

    @property
    def is_on(self) -> bool | None:
        """Return True while cooking."""
        zone = self.zone_snapshot
        return zone.is_cooking if zone else None


class OnlineSensor(TwinFryEntity, BinarySensorEntity):
    """Whether VeSync reports the fryer as connected."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "online"

    def __init__(self, data: TwinFryData) -> None:
        """Initialise the sensor."""
        super().__init__(data, "online")

    @property
    def available(self) -> bool:
        """Available whenever the VeSync cloud answered."""
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def is_on(self) -> bool | None:
        """Return True when the fryer is online."""
        data = self.coordinator.data
        return data.online if data else None
