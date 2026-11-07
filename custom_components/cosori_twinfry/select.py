"""Program choice per zone (staged for the next start)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant

from .const import Program
from .entity import TwinFryEntity
from .fryer_ext import supported_programs

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import TwinFryConfigEntry, TwinFryData

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TwinFryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selects."""
    data = entry.runtime_data
    async_add_entities([ProgramSelect(data, 1), ProgramSelect(data, 2)])


class ProgramSelect(TwinFryEntity, SelectEntity):
    """Program for the next start of a zone; picking one loads its defaults."""

    _attr_translation_key = "zone_program_setting"

    def __init__(self, data: TwinFryData, zone: int) -> None:
        """Initialise the select."""
        super().__init__(data, "program_setting", zone)
        self._attr_options = [p.value for p in supported_programs(data.coordinator.device)]

    async def async_added_to_hass(self) -> None:
        """Follow the controller."""
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        """Local setting, always editable."""
        return True

    @property
    def current_option(self) -> str:
        """Staged program."""
        return self.controller.settings[self.zone].program.value

    async def async_select_option(self, option: str) -> None:
        """Stage a program."""
        self.controller.async_set_program(self.zone, Program(option))
