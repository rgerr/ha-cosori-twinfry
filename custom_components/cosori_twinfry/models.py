"""Data models and pure helpers for the COSORI TwinFry integration.

Everything here is free of Home Assistant and network code so it can be unit
tested directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .const import (
    ACTIVE_STATUSES,
    FINISH_TOLERANCE,
    PROGRAM_API_MODE,
    PYVESYNC_STATUS_MAP,
    SYNC_TYPE_MAP,
    DeviceStatus,
    Program,
    StartOutcome,
    SyncMode,
    ZoneEvent,
    ZoneStatus,
)


def minutes_to_seconds(minutes: float) -> int:
    """Convert minutes to whole seconds."""
    return round(float(minutes) * 60)


def seconds_to_minutes(seconds: int | None) -> float | None:
    """Convert seconds to minutes, keeping None."""
    if seconds is None:
        return None
    return round(seconds / 60, 2)


def normalise_status(raw: Any) -> ZoneStatus:
    """Map a pyvesync cook status (enum or string) to a ZoneStatus."""
    if raw is None:
        return ZoneStatus.STANDBY
    value = getattr(raw, "value", raw)
    return PYVESYNC_STATUS_MAP.get(str(value), ZoneStatus.UNKNOWN)


def program_from_api_mode(api_mode: str | None) -> Program | None:
    """Return the Program for an API mode string, or None."""
    if not api_mode:
        return None
    for program, mode in PROGRAM_API_MODE.items():
        if mode.lower() == str(api_mode).lower():
            return program
    return None


def sync_mode_from_raw(sync_type: Any) -> SyncMode | None:
    """Return the SyncMode for a raw syncType value."""
    try:
        return SYNC_TYPE_MAP.get(int(sync_type))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class ZoneSnapshot:
    """Confirmed state of one zone at the time of a successful poll."""

    status: ZoneStatus
    available: bool = True
    program: Program | None = None
    api_mode: str | None = None
    recipe: str | None = None
    set_temperature: int | None = None
    set_time_s: int | None = None
    remaining_s: int | None = None
    total_remaining_s: int | None = None

    @property
    def is_active(self) -> bool:
        """Return True while a cook is running or paused."""
        return self.status in ACTIVE_STATUSES

    @property
    def is_cooking(self) -> bool:
        """Return True while cooking."""
        return self.status == ZoneStatus.COOKING

    def ends_at(self, polled_at: datetime) -> datetime | None:
        """Return when the cook is expected to finish (running cooks only)."""
        if self.status not in (ZoneStatus.COOKING, ZoneStatus.HOLD):
            return None
        remaining = (
            self.total_remaining_s if self.total_remaining_s is not None else self.remaining_s
        )
        if remaining is None:
            return None
        return polled_at + timedelta(seconds=remaining)


@dataclass(frozen=True, slots=True)
class FryerSnapshot:
    """Confirmed state of the fryer from one successful poll."""

    online: bool
    polled_at: datetime
    zone_1: ZoneSnapshot
    zone_2: ZoneSnapshot
    temp_unit: str = "c"
    sync_mode: SyncMode | None = None
    work_chamber: int | None = None

    def zone(self, number: int) -> ZoneSnapshot:
        """Return zone 1 or 2."""
        return self.zone_1 if number == 1 else self.zone_2

    @property
    def whole_basket(self) -> bool:
        """Return True while the divider is out (whole-basket cook)."""
        return self.work_chamber == 3

    @property
    def any_active(self) -> bool:
        """Return True if any zone is running or paused."""
        return self.zone_1.is_active or self.zone_2.is_active

    @property
    def device_status(self) -> DeviceStatus:
        """Return the combined status."""
        if not self.online:
            return DeviceStatus.OFFLINE
        statuses = {self.zone_1.status, self.zone_2.status}
        if ZoneStatus.COOKING in statuses or ZoneStatus.HOLD in statuses:
            return DeviceStatus.COOKING
        if ZoneStatus.PAUSED in statuses or ZoneStatus.BASKET_OUT in statuses:
            return DeviceStatus.PAUSED
        if ZoneStatus.READY in statuses:
            return DeviceStatus.READY
        return DeviceStatus.IDLE


class UnreadableStatusError(ValueError):
    """Raised when a poll response cannot be parsed."""


def _int_or_none(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _zone_from_item(item: dict[str, Any]) -> ZoneSnapshot:
    status = normalise_status(item.get("cookStatus"))
    if status == ZoneStatus.STANDBY:
        return ZoneSnapshot(status=status)
    api_mode = item.get("mode") or None
    return ZoneSnapshot(
        status=status,
        program=program_from_api_mode(api_mode),
        api_mode=api_mode,
        recipe=item.get("recipeName") or None,
        set_temperature=_int_or_none(item.get("cookTemp")) or None,
        set_time_s=_int_or_none(item.get("cookSetTime")),
        remaining_s=_int_or_none(item.get("currentRemainingTime")),
        total_remaining_s=_int_or_none(item.get("totalTimeRemaining")),
    )


def parse_multi_status(inner: dict[str, Any], polled_at: datetime) -> FryerSnapshot:
    """Build a snapshot from a ``getAirfryerMultiStatus`` inner result.

    Chamber 1 is the left zone, 2 the right zone and 3 the whole basket
    (divider removed), which is shown on zone 1 while zone 2 is unavailable.
    A chamber that is not listed is idle. Times are in seconds (TF101S).

    Raises:
        UnreadableStatusError: the response has no usable ``statusList``.
    """
    status_list = inner.get("statusList")
    if not isinstance(status_list, list):
        raise UnreadableStatusError("statusList missing")
    zones: dict[int, ZoneSnapshot] = {}
    for item in status_list:
        if not isinstance(item, dict):
            raise UnreadableStatusError("statusList item is not an object")
        chamber = _int_or_none(item.get("chamber"))
        if chamber not in (1, 2, 3):
            continue
        zones[chamber] = _zone_from_item(item)

    work_chamber = _int_or_none(inner.get("workChamber"))
    whole = work_chamber == 3 or (3 in zones and zones[3].status != ZoneStatus.STANDBY)
    idle = ZoneSnapshot(status=ZoneStatus.STANDBY)
    if whole:
        zone_1 = zones.get(3, zones.get(1, idle))
        zone_2 = ZoneSnapshot(status=ZoneStatus.STANDBY, available=False)
    else:
        zone_1 = zones.get(1, idle)
        zone_2 = zones.get(2, idle)
    unit = str(inner.get("tempUnit") or "c").lower()[:1]
    return FryerSnapshot(
        online=True,
        polled_at=polled_at,
        zone_1=zone_1,
        zone_2=zone_2,
        temp_unit=unit if unit in ("c", "f") else "c",
        sync_mode=sync_mode_from_raw(inner.get("syncType")),
        work_chamber=work_chamber or None,
    )


def offline_snapshot(polled_at: datetime) -> FryerSnapshot:
    """Return a snapshot for a fryer that VeSync reports as offline."""
    unknown = ZoneSnapshot(status=ZoneStatus.UNKNOWN, available=False)
    return FryerSnapshot(online=False, polled_at=polled_at, zone_1=unknown, zone_2=unknown)


def classify_transition(
    previous: ZoneSnapshot | None,
    current: ZoneSnapshot,
    elapsed_s: float,
) -> ZoneEvent | None:
    """Return the event for a zone status change between two polls.

    ``elapsed_s`` is the time between the two polls; it is used to decide
    whether a cook that disappeared had (almost) run out (finished) or was
    ended early (stopped).
    """
    if previous is None or previous.status == current.status:
        return None
    if current.status == ZoneStatus.READY:
        return ZoneEvent.READY
    if current.status == ZoneStatus.COOKING:
        if previous.status in (ZoneStatus.PAUSED, ZoneStatus.BASKET_OUT):
            return ZoneEvent.RESUMED
        if previous.status in (ZoneStatus.STANDBY, ZoneStatus.READY, ZoneStatus.UNKNOWN):
            return ZoneEvent.STARTED
        return None
    if current.status in (ZoneStatus.PAUSED, ZoneStatus.BASKET_OUT):
        if previous.status in (ZoneStatus.COOKING, ZoneStatus.HOLD):
            return ZoneEvent.PAUSED
        return None
    if current.status == ZoneStatus.STANDBY and previous.is_active:
        remaining = previous.remaining_s
        if previous.status in (ZoneStatus.COOKING, ZoneStatus.HOLD) and remaining is not None:
            remaining = remaining - elapsed_s
        if remaining is not None and remaining <= FINISH_TOLERANCE:
            return ZoneEvent.FINISHED
        return ZoneEvent.STOPPED
    return None


@dataclass(slots=True)
class ZoneSettings:
    """Settings staged for the next start of a zone."""

    program: Program = Program.AIRFRY
    temperature: int = 200
    minutes: int = 20

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "program": self.program.value,
            "temperature": self.temperature,
            "minutes": self.minutes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ZoneSettings:
        """Build from stored data, falling back to defaults."""
        if not data:
            return cls()
        try:
            return cls(
                program=Program(data.get("program", Program.AIRFRY)),
                temperature=int(data.get("temperature", 200)),
                minutes=int(data.get("minutes", 20)),
            )
        except (TypeError, ValueError):
            return cls()


@dataclass(slots=True)
class StartReport:
    """Report of the last start command, shown in Home Assistant."""

    outcome: StartOutcome = StartOutcome.NONE
    target: str | None = None
    method: str | None = None
    message: str | None = None
    steps: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return attributes for the result sensor."""
        return {
            "target": self.target,
            "method": self.method,
            "message": self.message,
            "steps": list(self.steps),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
