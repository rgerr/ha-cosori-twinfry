"""Start/stop buttons for the COSORI TwinFry integration.

Every start button is an explicit user command; nothing in this integration
starts a cook on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant

from .const import Zone
from .entity import TwinFryEntity

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import TwinFryConfigEntry, TwinFryData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class TwinFryButtonDescription(ButtonEntityDescription):
    """Describes a TwinFry button."""

    target: Zone
    start: bool
    zone: int | None = None


BUTTONS: tuple[TwinFryButtonDescription, ...] = (
    TwinFryButtonDescription(
        key="start", translation_key="zone_start", target=Zone.ZONE_1, start=True, zone=1
    ),
    TwinFryButtonDescription(
        key="start", translation_key="zone_start", target=Zone.ZONE_2, start=True, zone=2
    ),
    TwinFryButtonDescription(
        key="stop", translation_key="zone_stop", target=Zone.ZONE_1, start=False, zone=1
    ),
    TwinFryButtonDescription(
        key="stop", translation_key="zone_stop", target=Zone.ZONE_2, start=False, zone=2
    ),
    TwinFryButtonDescription(
        key="start_both", translation_key="start_both", target=Zone.BOTH, start=True
    ),
    TwinFryButtonDescription(
        key="match_start", translation_key="match_start", target=Zone.MATCH, start=True
    ),
    TwinFryButtonDescription(
        key="stop_both", translation_key="stop_both", target=Zone.BOTH, start=False
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TwinFryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    data = entry.runtime_data
    async_add_entities(TwinFryButton(data, description) for description in BUTTONS)


class TwinFryButton(TwinFryEntity, ButtonEntity):
    """Start or stop button."""

    entity_description: TwinFryButtonDescription

    def __init__(self, data: TwinFryData, description: TwinFryButtonDescription) -> None:
        """Initialise the button."""
        super().__init__(data, description.key, description.zone)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Stop buttons for zone 2 stay usable in whole-basket mode."""
        if self.entity_description.zone == 2 and not self.entity_description.start:
            return (
                self.coordinator.last_update_success
                and self.coordinator.data is not None
                and self.coordinator.data.online
            )
        return super().available

    async def async_press(self) -> None:
        """Run the command; errors are shown to the user."""
        if self.entity_description.start:
            await self.controller.async_start(self.entity_description.target)
        else:
            await self.controller.async_stop(self.entity_description.target)
