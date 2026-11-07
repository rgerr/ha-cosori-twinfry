"""Start/stop orchestration for the COSORI TwinFry integration.

A start is only reported as successful when a fresh, successful VeSync poll
shows the zone(s) cooking. An accepted API call is never treated as a start.

Start routes
------------
native     ``startMultiCook`` with ``readyStart: false``, then confirm.
switchbot  ``startMultiCook`` with ``readyStart: true``, confirm the fryer is
           ``ready`` (waiting for its start button), press the configured
           SwitchBot Bot, then confirm cooking.
auto       native first; if the fryer waits in ``ready`` it presses the
           SwitchBot, and if the native command does nothing it falls back to
           the full SwitchBot route. Without a SwitchBot it behaves as native.

Safety rules
------------
* One start at a time (``start_in_progress``); a second request is refused,
  never queued, so a double tap cannot start twice.
* A zone that is cooking, paused or has its basket out is never restarted.
* The SwitchBot is only pressed when the target zone is confirmed ``ready``
  and no other zone is active: the physical Start/Pause button might pause a
  running zone, which has not been verified on hardware.
* Stopping is never blocked by a running start.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from pyvesync.const import AirFryerChamber

from .const import (
    CONF_CONFIRM_TIMEOUT,
    CONF_PRESS_DELAY,
    CONF_READY_TIMEOUT,
    CONF_START_METHOD,
    CONF_SWITCHBOT_ENTITY,
    CONFIRM_POLL_INTERVAL,
    DEFAULT_CONFIRM_TIMEOUT,
    DEFAULT_PRESS_DELAY,
    DEFAULT_READY_TIMEOUT,
    DOMAIN,
    PRESS_TIMEOUT,
    PROGRAM_MAX_MINUTES,
    STARTABLE_STATUSES,
    STORAGE_VERSION,
    SWITCHBOT_DOMAINS,
    Program,
    StartMethod,
    StartOutcome,
    Zone,
    ZoneStatus,
)
from .fryer_ext import (
    InvalidSettingsError,
    async_send_start,
    build_recipe,
    check_compatible,
    default_settings,
    last_error,
    supported_programs,
    temp_limits,
)
from .models import FryerSnapshot, StartReport, ZoneSettings

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from pyvesync.const import AirFryerPresetRecipe

    from .coordinator import TwinFryCoordinator

_LOGGER = logging.getLogger(__name__)


class TwinFryError(HomeAssistantError):
    """Translated error raised by start/stop commands."""

    def __init__(self, key: str, **placeholders: Any) -> None:
        """Create the error with a translation key."""
        super().__init__(
            translation_domain=DOMAIN,
            translation_key=key,
            translation_placeholders={k: str(v) for k, v in placeholders.items()},
        )
        self.key = key


@dataclass(frozen=True, slots=True)
class _Step:
    """One startMultiCook request and the zones it must start."""

    chamber: AirFryerChamber
    zones: tuple[int, ...]
    recipe: AirFryerPresetRecipe


class TwinFryController:
    """Owns the staged settings and runs start/stop commands."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: TwinFryCoordinator,
    ) -> None:
        """Initialise the controller."""
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.device = coordinator.device
        self.settings: dict[int, ZoneSettings] = {1: ZoneSettings(), 2: ZoneSettings()}
        self.report = StartReport()
        self.confirm_poll_interval: float = CONFIRM_POLL_INTERVAL
        self._start_lock = asyncio.Lock()
        self._stop_lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

    # ------------------------------------------------------------------ setup

    async def async_load(self) -> None:
        """Load staged settings and make them valid for this fryer."""
        stored = await self._store.async_load() or {}
        for zone in (1, 2):
            self.settings[zone] = self._sanitise(ZoneSettings.from_dict(stored.get(f"zone_{zone}")))

    def _sanitise(self, settings: ZoneSettings) -> ZoneSettings:
        programs = supported_programs(self.device)
        if settings.program not in programs:
            settings.program = programs[0]
            temp, minutes = default_settings(self.device, settings.program)
            settings.temperature, settings.minutes = temp, minutes
        low, high, step = temp_limits(self.device, settings.program)
        settings.temperature = min(high, max(low, round(settings.temperature / step) * step))
        settings.minutes = min(PROGRAM_MAX_MINUTES[settings.program], max(1, settings.minutes))
        return settings

    def _stored(self) -> dict[str, Any]:
        return {f"zone_{z}": s.as_dict() for z, s in self.settings.items()}

    @callback
    def _async_save(self) -> None:
        self._store.async_delay_save(self._stored, 1)

    async def async_unload(self) -> None:
        """Write pending settings before the entry unloads."""
        await self._store.async_save(self._stored())

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Listen for settings or start-report changes."""
        self._listeners.append(listener)

        @callback
        def _remove() -> None:
            self._listeners.remove(listener)

        return _remove

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    # --------------------------------------------------------------- options

    @property
    def start_method(self) -> StartMethod:
        """Configured start method."""
        return StartMethod(self.entry.options.get(CONF_START_METHOD, StartMethod.NATIVE))

    @property
    def switchbot_entity(self) -> str | None:
        """Configured SwitchBot entity id, if any."""
        return self.entry.options.get(CONF_SWITCHBOT_ENTITY) or None

    @property
    def _press_delay(self) -> float:
        return float(self.entry.options.get(CONF_PRESS_DELAY, DEFAULT_PRESS_DELAY))

    @property
    def _ready_timeout(self) -> float:
        return float(self.entry.options.get(CONF_READY_TIMEOUT, DEFAULT_READY_TIMEOUT))

    @property
    def _confirm_timeout(self) -> float:
        return float(self.entry.options.get(CONF_CONFIRM_TIMEOUT, DEFAULT_CONFIRM_TIMEOUT))

    @property
    def is_starting(self) -> bool:
        """Return True while a start command runs."""
        return self._start_lock.locked()

    # -------------------------------------------------------------- settings

    def temperature_limits(self, zone: int) -> tuple[int, int, int]:
        """Return (min, max, step) for the zone's staged program."""
        return temp_limits(self.device, self.settings[zone].program)

    @callback
    def async_set_program(self, zone: int, program: Program) -> None:
        """Stage a program; temperature and time take the program defaults."""
        if program not in supported_programs(self.device):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="program_not_supported",
                translation_placeholders={"program": program.value},
            )
        temp, minutes = default_settings(self.device, program)
        self.settings[zone] = ZoneSettings(program=program, temperature=temp, minutes=minutes)
        self._async_save()
        self._notify()

    @callback
    def async_set_temperature(self, zone: int, temperature: float) -> None:
        """Stage a temperature (validated against the program's limits)."""
        settings = self.settings[zone]
        try:
            recipe = build_recipe(self.device, settings.program, int(temperature), settings.minutes)
        except InvalidSettingsError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=err.key,
                translation_placeholders=err.placeholders,
            ) from err
        settings.temperature = int(recipe.target_temp)
        self._async_save()
        self._notify()

    @callback
    def async_set_minutes(self, zone: int, minutes: float) -> None:
        """Stage a cook time in minutes."""
        settings = self.settings[zone]
        try:
            build_recipe(self.device, settings.program, settings.temperature, int(minutes))
        except InvalidSettingsError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=err.key,
                translation_placeholders=err.placeholders,
            ) from err
        settings.minutes = int(minutes)
        self._async_save()
        self._notify()

    def _recipe(self, zone: int) -> AirFryerPresetRecipe:
        settings = self.settings[zone]
        try:
            return build_recipe(
                self.device, settings.program, settings.temperature, settings.minutes
            )
        except InvalidSettingsError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=err.key,
                translation_placeholders=err.placeholders,
            ) from err

    # ----------------------------------------------------------------- start

    async def async_start(self, target: Zone, method: StartMethod | None = None) -> str:
        """Start a cook and return the method that started it.

        Raises TwinFryError (or ServiceValidationError) with a clear reason
        when the start is not confirmed.
        """
        if self._start_lock.locked():
            raise TwinFryError("start_in_progress")
        async with self._start_lock:
            method = method or self.start_method
            report = StartReport(
                outcome=StartOutcome.IN_PROGRESS,
                target=target.value,
                method=method.value,
                started_at=dt_util.utcnow(),
            )
            self.report = report
            self._notify()
            try:
                used = await self._async_start_locked(target, method, report)
            except HomeAssistantError as err:
                report.outcome = StartOutcome.FAILED
                report.message = str(err) or getattr(err, "translation_key", None)
                report.finished_at = dt_util.utcnow()
                _LOGGER.warning(
                    "Start %s via %s not confirmed: %s",
                    target.value,
                    method.value,
                    getattr(err, "translation_key", err),
                )
                self._notify()
                raise
            report.outcome = StartOutcome.SUCCESS
            report.method = used
            report.message = None
            report.finished_at = dt_util.utcnow()
            self._notify()
            return used

    async def _async_start_locked(
        self, target: Zone, method: StartMethod, report: StartReport
    ) -> str:
        # 1. Reachable and online?
        snapshot = await self._async_fresh_snapshot()
        report.steps.append("device_reachable")

        # 2. Valid settings -> requests to send.
        steps = self._plan(target, method)
        report.steps.append("settings_valid")

        # 3. Zones in a startable state? (prevents a double start)
        involved = {z for step in steps for z in step.zones}
        if target in (Zone.MATCH, Zone.WHOLE, Zone.BOTH):
            involved = {1, 2}
        for zone in sorted(involved):
            if snapshot.zone(zone).status not in STARTABLE_STATUSES:
                raise TwinFryError("zone_busy", zone=zone, status=snapshot.zone(zone).status.value)

        if method == StartMethod.SWITCHBOT:
            self._validate_switchbot()
            self._guard_other_zones(snapshot, involved)

        used: set[str] = set()
        for step in steps:
            used.add(await self._async_run_step(step, method, report))
        return "+".join(sorted(used))

    def _plan(self, target: Zone, method: StartMethod) -> list[_Step]:
        if target == Zone.ZONE_1:
            return [_Step(AirFryerChamber.CHAMBER_1, (1,), self._recipe(1))]
        if target == Zone.ZONE_2:
            return [_Step(AirFryerChamber.CHAMBER_2, (2,), self._recipe(2))]
        if target == Zone.WHOLE:
            return [_Step(AirFryerChamber.WHOLE, (1,), self._recipe(1))]
        if target == Zone.MATCH:
            return [_Step(AirFryerChamber.BOTH, (1, 2), self._recipe(1))]
        # BOTH: independent zones. With a physical start button involved, one
        # combined program and one press is the only safe way, which needs
        # identical settings.
        recipe_1, recipe_2 = self._recipe(1), self._recipe(2)
        if method != StartMethod.NATIVE and self.settings[1] == self.settings[2]:
            return [_Step(AirFryerChamber.BOTH, (1, 2), recipe_1)]
        if method == StartMethod.SWITCHBOT:
            raise TwinFryError("both_needs_equal_settings")
        return [
            _Step(AirFryerChamber.CHAMBER_1, (1,), recipe_1),
            _Step(AirFryerChamber.CHAMBER_2, (2,), recipe_2),
        ]

    async def _async_run_step(self, step: _Step, method: StartMethod, report: StartReport) -> str:
        label = f"chamber_{int(step.chamber)}"
        has_switchbot = self.switchbot_entity is not None
        if method == StartMethod.SWITCHBOT:
            return await self._async_switchbot_route(step, report, programmed=False)

        # Native (or the first half of auto).
        accepted = await self._async_send(step, ready_start=False)
        report.steps.append(f"{label}_native_{'accepted' if accepted else 'rejected'}")
        if not accepted:
            if method == StartMethod.AUTO and has_switchbot:
                return await self._async_switchbot_route(step, report, programmed=False)
            raise TwinFryError("command_rejected", error=last_error(self.device))

        status = await self._async_wait(
            step.zones,
            until=ZoneStatus.COOKING,
            also=ZoneStatus.READY,
            limit=self._confirm_timeout,
        )
        if status == ZoneStatus.COOKING:
            report.steps.append(f"{label}_cooking_confirmed")
            return StartMethod.NATIVE.value
        if status == ZoneStatus.READY:
            report.steps.append(f"{label}_waiting_for_start_button")
            if method == StartMethod.AUTO and has_switchbot:
                return await self._async_switchbot_route(step, report, programmed=True)
            raise TwinFryError("waiting_for_button")
        report.steps.append(f"{label}_native_not_confirmed")
        if method == StartMethod.AUTO and has_switchbot:
            return await self._async_switchbot_route(step, report, programmed=False)
        raise TwinFryError("start_not_confirmed", timeout=int(self._confirm_timeout))

    async def _async_switchbot_route(
        self, step: _Step, report: StartReport, *, programmed: bool
    ) -> str:
        label = f"chamber_{int(step.chamber)}"
        self._validate_switchbot()
        if not programmed:
            if not check_compatible(self.device):
                raise TwinFryError("ready_start_unavailable")
            accepted = await self._async_send(step, ready_start=True)
            report.steps.append(f"{label}_ready_{'accepted' if accepted else 'rejected'}")
            if not accepted:
                raise TwinFryError("command_rejected", error=last_error(self.device))
            status = await self._async_wait(
                step.zones,
                until=ZoneStatus.READY,
                also=ZoneStatus.COOKING,
                limit=self._ready_timeout,
            )
            if status == ZoneStatus.COOKING:
                # The fryer started without its button: still a confirmed start.
                report.steps.append(f"{label}_cooking_confirmed_without_press")
                return StartMethod.NATIVE.value
            if status != ZoneStatus.READY:
                raise TwinFryError("not_ready", timeout=int(self._ready_timeout))
            report.steps.append(f"{label}_ready_confirmed")

        snapshot = self.coordinator.data
        if snapshot is None:
            raise TwinFryError("not_reachable", error="no data")
        self._guard_other_zones(snapshot, set(step.zones))

        if self._press_delay > 0:
            await asyncio.sleep(self._press_delay)
        await self._async_press()
        report.steps.append("switchbot_pressed")

        status = await self._async_wait(
            step.zones, until=ZoneStatus.COOKING, limit=self._confirm_timeout
        )
        if status != ZoneStatus.COOKING:
            raise TwinFryError("not_confirmed_after_press", timeout=int(self._confirm_timeout))
        report.steps.append(f"{label}_cooking_confirmed")
        return StartMethod.SWITCHBOT.value

    async def _async_send(self, step: _Step, *, ready_start: bool) -> bool:
        try:
            async with asyncio.timeout(PRESS_TIMEOUT + 10):
                return await async_send_start(
                    self.device, step.recipe, step.chamber, ready_start=ready_start
                )
        except TimeoutError as err:
            raise TwinFryError("command_timeout") from err
        except HomeAssistantError:
            raise
        except Exception as err:
            raise TwinFryError("command_rejected", error=type(err).__name__) from err

    async def _async_fresh_snapshot(self) -> FryerSnapshot:
        await self.coordinator.async_refresh()
        if not self.coordinator.last_update_success or self.coordinator.data is None:
            raise TwinFryError("not_reachable", error=self.coordinator.last_error or "unknown")
        if not self.coordinator.data.online:
            raise TwinFryError("device_offline")
        return self.coordinator.data

    async def _async_wait(
        self,
        zones: tuple[int, ...],
        *,
        until: ZoneStatus,
        also: ZoneStatus | None = None,
        limit: float,
    ) -> ZoneStatus | None:
        """Poll until all zones report ``until`` (or all ``also``)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + limit
        while True:
            await asyncio.sleep(self.confirm_poll_interval)
            await self.coordinator.async_refresh()
            data = self.coordinator.data
            if self.coordinator.last_update_success and data is not None and data.online:
                statuses = {data.zone(z).status for z in zones}
                if statuses == {until}:
                    return until
                if also is not None and statuses == {also}:
                    return also
            if loop.time() >= deadline:
                return None

    def _guard_other_zones(self, snapshot: FryerSnapshot, involved: set[int]) -> None:
        for zone in (1, 2):
            if zone not in involved and snapshot.zone(zone).is_active:
                raise TwinFryError("other_zone_active", zone=zone)

    # -------------------------------------------------------------- switchbot

    def _validate_switchbot(self) -> str:
        entity_id = self.switchbot_entity
        if not entity_id:
            raise TwinFryError("switchbot_not_configured")
        domain = entity_id.split(".", 1)[0]
        if domain not in SWITCHBOT_DOMAINS:
            raise TwinFryError("switchbot_wrong_domain", entity_id=entity_id)
        state = self.hass.states.get(entity_id)
        # A button that was never pressed has state "unknown"; that is fine.
        if state is None or state.state == STATE_UNAVAILABLE:
            raise TwinFryError("switchbot_unavailable", entity_id=entity_id)
        if domain == "switch" and state.attributes.get("switch_mode") is True:
            # In switch mode turn_on keeps the arm down instead of one press.
            raise TwinFryError("switchbot_switch_mode", entity_id=entity_id)
        return entity_id

    async def _async_press(self) -> None:
        entity_id = self._validate_switchbot()
        domain = entity_id.split(".", 1)[0]
        service = "press" if domain == "button" else "turn_on"
        try:
            async with asyncio.timeout(PRESS_TIMEOUT):
                await self.hass.services.async_call(
                    domain, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
                )
        except TimeoutError as err:
            raise TwinFryError("switchbot_failed", entity_id=entity_id, error="timeout") from err
        except HomeAssistantError as err:
            raise TwinFryError(
                "switchbot_failed", entity_id=entity_id, error=type(err).__name__
            ) from err
        state = self.hass.states.get(entity_id)
        if state is not None and state.attributes.get("last_run_success") is False:
            raise TwinFryError(
                "switchbot_failed", entity_id=entity_id, error="last_run_success false"
            )

    # ------------------------------------------------------------------ stop

    async def async_stop(self, target: Zone) -> None:
        """End the cook (or a loaded ``ready`` program) and confirm standby."""
        async with self._stop_lock:
            snapshot = await self._async_fresh_snapshot()
            if target == Zone.ZONE_1:
                zones: tuple[int, ...] = (1,)
            elif target == Zone.ZONE_2:
                zones = (2,)
            else:
                zones = (1, 2)
            to_stop = [z for z in zones if snapshot.zone(z).status != ZoneStatus.STANDBY]
            if not to_stop:
                return
            for zone in to_stop:
                # CHAMBER_1 ends the whole basket while one is running
                # (pyvesync reads workChamber from the poll above).
                chamber = AirFryerChamber.CHAMBER_1 if zone == 1 else AirFryerChamber.CHAMBER_2
                try:
                    async with asyncio.timeout(PRESS_TIMEOUT + 10):
                        ok = await self.device.end(chamber)
                except TimeoutError as err:
                    raise TwinFryError("command_timeout") from err
                if not ok:
                    raise TwinFryError("stop_rejected", zone=zone, error=last_error(self.device))
            status = await self._async_wait(
                tuple(to_stop), until=ZoneStatus.STANDBY, limit=self._confirm_timeout
            )
            if status != ZoneStatus.STANDBY:
                raise TwinFryError("stop_not_confirmed", timeout=int(self._confirm_timeout))
