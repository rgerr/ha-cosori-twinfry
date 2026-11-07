"""DataUpdateCoordinator for the COSORI TwinFry integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pyvesync.utils.errors import VeSyncError, VeSyncLoginError, VeSyncTokenError

from .const import (
    API_TIMEOUT,
    CONF_SCAN_INTERVAL_ACTIVE,
    CONF_SCAN_INTERVAL_IDLE,
    DEFAULT_SCAN_INTERVAL_ACTIVE,
    DEFAULT_SCAN_INTERVAL_IDLE,
    DOMAIN,
    EVENT_TWINFRY,
    ZoneEvent,
)
from .fryer_ext import last_error, last_poll_inner_result
from .models import (
    FryerSnapshot,
    UnreadableStatusError,
    classify_transition,
    offline_snapshot,
    parse_multi_status,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from pyvesync import VeSync
    from pyvesync.devices.vesynckitchen import VeSyncDualAirFryer

_LOGGER = logging.getLogger(__name__)

ZoneEventListener = Callable[[int, ZoneEvent, dict[str, Any]], None]


class TwinFryCoordinator(DataUpdateCoordinator[FryerSnapshot]):
    """Poll the fryer and publish only confirmed state.

    Every snapshot comes from one successful ``getAirfryerMultiStatus`` poll.
    A failed poll raises ``UpdateFailed``, which makes all entities
    unavailable instead of showing the previous values as if they were
    current. pyvesync's own local state (which it sets optimistically after a
    command) is never read.
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        manager: VeSync,
        device: VeSyncDualAirFryer,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {device.device_name}",
            update_interval=timedelta(seconds=self._idle_interval(entry)),
            always_update=True,
        )
        self.manager = manager
        self.device = device
        self._event_listeners: list[ZoneEventListener] = []
        self.last_error: str | None = None

    @staticmethod
    def _idle_interval(entry: ConfigEntry) -> int:
        return int(entry.options.get(CONF_SCAN_INTERVAL_IDLE, DEFAULT_SCAN_INTERVAL_IDLE))

    @staticmethod
    def _active_interval(entry: ConfigEntry) -> int:
        return int(entry.options.get(CONF_SCAN_INTERVAL_ACTIVE, DEFAULT_SCAN_INTERVAL_ACTIVE))

    @callback
    def async_add_zone_event_listener(self, listener: ZoneEventListener) -> CALLBACK_TYPE:
        """Register a listener for zone events; returns a remover."""
        self._event_listeners.append(listener)

        @callback
        def _remove() -> None:
            self._event_listeners.remove(listener)

        return _remove

    async def _async_update_data(self) -> FryerSnapshot:
        """Fetch a fresh, confirmed snapshot."""
        try:
            async with asyncio.timeout(API_TIMEOUT):
                snapshot = await self._async_poll()
        except (VeSyncLoginError, VeSyncTokenError) as err:
            self.last_error = type(err).__name__
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except TimeoutError as err:
            self.last_error = "timeout"
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="poll_timeout") from err
        except (VeSyncError, aiohttp.ClientError) as err:
            self.last_error = f"{type(err).__name__}: {err}"
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="poll_failed",
                translation_placeholders={"error": type(err).__name__},
            ) from err

        self.last_error = None
        self._async_emit_events(self.data, snapshot)
        self._async_adjust_interval(snapshot)
        return snapshot

    async def _async_poll(self) -> FryerSnapshot:
        device = self.device
        device.last_response = None
        await device.update()
        now = dt_util.utcnow()
        info = device.last_response
        if info is None:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="poll_failed",
                translation_placeholders={"error": "no response"},
            )
        if getattr(info, "device_online", True) is False:
            _LOGGER.debug("%s reported offline by VeSync", device.device_name)
            return offline_snapshot(now)
        inner = last_poll_inner_result(device)
        if inner is None:
            self.last_error = last_error(device)
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="poll_failed",
                translation_placeholders={"error": self.last_error},
            )
        try:
            return parse_multi_status(inner, now)
        except UnreadableStatusError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="poll_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    @callback
    def _async_adjust_interval(self, snapshot: FryerSnapshot) -> None:
        seconds = (
            self._active_interval(self.config_entry)
            if snapshot.any_active or snapshot.device_status == "ready"
            else self._idle_interval(self.config_entry)
        )
        self.update_interval = timedelta(seconds=seconds)

    @callback
    def _async_emit_events(self, previous: FryerSnapshot | None, current: FryerSnapshot) -> None:
        """Fire zone events for status changes between two confirmed polls."""
        if previous is None or not previous.online or not current.online:
            return
        elapsed = (current.polled_at - previous.polled_at).total_seconds()
        for number in (1, 2):
            event = classify_transition(previous.zone(number), current.zone(number), elapsed)
            if event is None:
                continue
            zone = current.zone(number)
            data: dict[str, Any] = {
                "device_id": self._device_registry_id(),
                "zone": number,
                "event": event.value,
                "previous_status": previous.zone(number).status.value,
                "status": zone.status.value,
                "program": zone.program.value if zone.program else None,
            }
            self.hass.bus.async_fire(EVENT_TWINFRY, data)
            for listener in list(self._event_listeners):
                listener(number, event, data)

    def _device_registry_id(self) -> str | None:
        registry = dr.async_get(self.hass)
        identifier = (DOMAIN, self.device.cid)
        if hasattr(registry, "async_get_device_by_identifier"):  # HA 2026.10+
            entry = registry.async_get_device_by_identifier(identifier, self.config_entry.entry_id)
        else:  # pragma: no cover - older Home Assistant
            entry = registry.async_get_device(identifiers={identifier})
        return entry.id if entry else None
