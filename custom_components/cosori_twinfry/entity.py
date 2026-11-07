"""Base entity for the COSORI TwinFry integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_NAME
from .coordinator import TwinFryCoordinator
from .models import ZoneSnapshot

if TYPE_CHECKING:
    from . import TwinFryData


class TwinFryEntity(CoordinatorEntity[TwinFryCoordinator]):
    """Entity bound to one fryer, optionally to one zone."""

    _attr_has_entity_name = True

    def __init__(self, data: TwinFryData, key: str, zone: int | None = None) -> None:
        """Initialise the entity."""
        super().__init__(data.coordinator)
        self.controller = data.controller
        self.zone = zone
        device = data.coordinator.device
        self._attr_unique_id = f"{device.cid}_zone_{zone}_{key}" if zone else f"{device.cid}_{key}"
        if zone is not None:
            self._attr_translation_placeholders = {"zone": str(zone)}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.cid)},
            manufacturer=MANUFACTURER,
            model=MODEL_NAME,
            model_id=device.device_type,
            name=device.device_name,
            sw_version=getattr(device, "current_firm_version", None),
        )

    @property
    def zone_snapshot(self) -> ZoneSnapshot | None:
        """Confirmed state of this entity's zone, if any."""
        data = self.coordinator.data
        if data is None or self.zone is None:
            return None
        return data.zone(self.zone)

    @property
    def available(self) -> bool:
        """Available only with a fresh, successful poll of an online fryer."""
        if not super().available or self.coordinator.data is None:
            return False
        if not self.coordinator.data.online:
            return False
        if self.zone is not None:
            snapshot = self.zone_snapshot
            return snapshot is not None and snapshot.available
        return True
