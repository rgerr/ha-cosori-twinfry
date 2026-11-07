"""Sensors for the COSORI TwinFry integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant

from .const import DeviceStatus, Program, StartOutcome, SyncMode, ZoneStatus
from .entity import TwinFryEntity
from .models import FryerSnapshot, ZoneSnapshot

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import TwinFryConfigEntry, TwinFryData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ZoneSensorDescription(SensorEntityDescription):
    """Describes a per-zone sensor."""

    value_fn: Callable[[ZoneSnapshot, FryerSnapshot], Any]


def _while_loaded(
    fn: Callable[[ZoneSnapshot], Any],
) -> Callable[[ZoneSnapshot, FryerSnapshot], Any]:
    """Return the value only when a cook is loaded (not in standby)."""

    def wrapper(zone: ZoneSnapshot, _data: FryerSnapshot) -> Any:
        if zone.status in (ZoneStatus.STANDBY, ZoneStatus.UNKNOWN):
            return None
        return fn(zone)

    return wrapper


ZONE_SENSORS: tuple[ZoneSensorDescription, ...] = (
    ZoneSensorDescription(
        key="status",
        translation_key="zone_status",
        device_class=SensorDeviceClass.ENUM,
        options=[s.value for s in ZoneStatus],
        value_fn=lambda zone, _d: zone.status.value,
    ),
    ZoneSensorDescription(
        key="program",
        translation_key="zone_program",
        device_class=SensorDeviceClass.ENUM,
        options=[p.value for p in Program],
        value_fn=_while_loaded(lambda zone: zone.program.value if zone.program else None),
    ),
    ZoneSensorDescription(
        key="set_temperature",
        translation_key="zone_set_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=_while_loaded(lambda zone: zone.set_temperature),
    ),
    ZoneSensorDescription(
        key="set_time",
        translation_key="zone_set_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=_while_loaded(lambda zone: zone.set_time_s),
    ),
    ZoneSensorDescription(
        key="remaining_time",
        translation_key="zone_remaining_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=_while_loaded(lambda zone: zone.remaining_s),
    ),
    ZoneSensorDescription(
        key="ends_at",
        translation_key="zone_ends_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda zone, data: zone.ends_at(data.polled_at),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TwinFryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    data = entry.runtime_data
    entities: list[SensorEntity] = [
        ZoneSensor(data, description, zone) for zone in (1, 2) for description in ZONE_SENSORS
    ]
    entities += [
        DeviceStatusSensor(data),
        SyncModeSensor(data),
        LastPollSensor(data),
        LastStartSensor(data),
    ]
    async_add_entities(entities)


class ZoneSensor(TwinFryEntity, SensorEntity):
    """A per-zone value from the last confirmed poll."""

    entity_description: ZoneSensorDescription

    def __init__(self, data: TwinFryData, description: ZoneSensorDescription, zone: int) -> None:
        """Initialise the sensor."""
        super().__init__(data, description.key, zone)
        self.entity_description = description

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Temperature follows the unit the fryer reports."""
        if self.entity_description.device_class == SensorDeviceClass.TEMPERATURE:
            data = self.coordinator.data
            if data is not None and data.temp_unit == "f":
                return UnitOfTemperature.FAHRENHEIT
            return UnitOfTemperature.CELSIUS
        return self.entity_description.native_unit_of_measurement

    @property
    def native_value(self) -> Any:
        """Return the value."""
        zone = self.zone_snapshot
        if zone is None or self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(zone, self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the recipe name on the program sensor."""
        if self.entity_description.key != "program":
            return None
        zone = self.zone_snapshot
        return {
            "recipe": zone.recipe if zone else None,
            "api_mode": zone.api_mode if zone else None,
        }


class DeviceStatusSensor(TwinFryEntity, SensorEntity):
    """Combined status; shows 'offline' while VeSync reports the fryer offline."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [s.value for s in DeviceStatus]
    _attr_translation_key = "device_status"

    def __init__(self, data: TwinFryData) -> None:
        """Initialise the sensor."""
        super().__init__(data, "status")

    @property
    def available(self) -> bool:
        """Available whenever the cloud answered (also when the fryer is offline)."""
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self) -> str | None:
        """Return the combined status."""
        data = self.coordinator.data
        return data.device_status.value if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Extra context for dashboards and automations."""
        data = self.coordinator.data
        if data is None:
            return None
        return {
            "whole_basket": data.whole_basket,
            "zone_1": data.zone_1.status.value,
            "zone_2": data.zone_2.status.value,
            "start_in_progress": self.controller.is_starting,
        }


class SyncModeSensor(TwinFryEntity, SensorEntity):
    """The syncType the fryer reports (off / match / sync)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [s.value for s in SyncMode]
    _attr_translation_key = "sync_mode"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, data: TwinFryData) -> None:
        """Initialise the sensor."""
        super().__init__(data, "sync_mode")

    @property
    def native_value(self) -> str | None:
        """Return the reported sync mode."""
        data = self.coordinator.data
        return data.sync_mode.value if data and data.sync_mode else None


class LastPollSensor(TwinFryEntity, SensorEntity):
    """Time of the last successful poll (to spot stale data)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_poll"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, data: TwinFryData) -> None:
        """Initialise the sensor."""
        super().__init__(data, "last_poll")

    @property
    def available(self) -> bool:
        """Keep showing when the last good poll was, even after failures."""
        return self.coordinator.data is not None

    @property
    def native_value(self) -> datetime | None:
        """Return the poll time."""
        data = self.coordinator.data
        return data.polled_at if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Report whether the latest poll failed."""
        return {
            "last_poll_successful": self.coordinator.last_update_success,
            "last_error": self.coordinator.last_error,
        }


class LastStartSensor(TwinFryEntity, SensorEntity):
    """Outcome of the last start command."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [s.value for s in StartOutcome]
    _attr_translation_key = "last_start"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, data: TwinFryData) -> None:
        """Initialise the sensor."""
        super().__init__(data, "last_start")

    async def async_added_to_hass(self) -> None:
        """Follow the controller."""
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        """A local report; always available."""
        return True

    @property
    def native_value(self) -> str:
        """Return the outcome."""
        return self.controller.report.outcome.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the details."""
        return self.controller.report.as_dict()
