"""Zone events (started, finished, stopped, ...) from confirmed polls."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback

from .const import ZoneEvent
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
    """Set up the event entities."""
    data = entry.runtime_data
    async_add_entities([ZoneEventEntity(data, 1), ZoneEventEntity(data, 2)])


class ZoneEventEntity(TwinFryEntity, EventEntity):
    """Fires when a zone starts, pauses, resumes, finishes or is stopped."""

    _attr_event_types = [e.value for e in ZoneEvent]
    _attr_translation_key = "zone_event"

    def __init__(self, data: TwinFryData, zone: int) -> None:
        """Initialise the entity."""
        super().__init__(data, "event", zone)

    async def async_added_to_hass(self) -> None:
        """Listen for zone transitions."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_zone_event_listener(self._handle_zone_event)
        )

    @property
    def available(self) -> bool:
        """Events stay available while the cloud answers."""
        return self.coordinator.last_update_success

    @callback
    def _handle_zone_event(self, zone: int, event: ZoneEvent, data: dict[str, Any]) -> None:
        if zone != self.zone:
            return
        self._trigger_event(
            event.value,
            {k: v for k, v in data.items() if k not in ("device_id", "event")},
        )
        self.async_write_ha_state()
