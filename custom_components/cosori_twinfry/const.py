"""Constants for the COSORI TwinFry integration."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

DOMAIN: Final = "cosori_twinfry"
MANUFACTURER: Final = "COSORI"
MODEL_NAME: Final = "Dual Blaze TwinFry 10L"

CONF_COUNTRY_CODE: Final = "country_code"
CONF_DEVICE_CID: Final = "device_cid"

# Options
CONF_START_METHOD: Final = "start_method"
CONF_SWITCHBOT_ENTITY: Final = "switchbot_entity"
CONF_PRESS_DELAY: Final = "press_delay"
CONF_READY_TIMEOUT: Final = "ready_timeout"
CONF_CONFIRM_TIMEOUT: Final = "confirm_timeout"
CONF_SCAN_INTERVAL_ACTIVE: Final = "scan_interval_active"
CONF_SCAN_INTERVAL_IDLE: Final = "scan_interval_idle"

DEFAULT_PRESS_DELAY: Final = 2
DEFAULT_READY_TIMEOUT: Final = 20
DEFAULT_CONFIRM_TIMEOUT: Final = 45
DEFAULT_SCAN_INTERVAL_ACTIVE: Final = 15
DEFAULT_SCAN_INTERVAL_IDLE: Final = 60

# Hard limits
API_TIMEOUT: Final = 30  # seconds for a single VeSync call
PRESS_TIMEOUT: Final = 20  # seconds for the SwitchBot service call
CONFIRM_POLL_INTERVAL: Final = 3  # seconds between polls while confirming
FINISH_TOLERANCE: Final = 90  # seconds left that still count as "finished"

SWITCHBOT_DOMAINS: Final = ("button", "switch")

STORAGE_VERSION: Final = 1

EVENT_TWINFRY: Final = f"{DOMAIN}_event"


class StartMethod(StrEnum):
    """How a cook is started."""

    NATIVE = "native"
    SWITCHBOT = "switchbot"
    AUTO = "auto"


class Zone(StrEnum):
    """Targets of a start or stop command."""

    ZONE_1 = "zone_1"
    ZONE_2 = "zone_2"
    BOTH = "both"
    MATCH = "match"
    WHOLE = "whole"


class ZoneStatus(StrEnum):
    """Normalised cook status of one zone (from a confirmed poll)."""

    STANDBY = "standby"
    READY = "ready"
    COOKING = "cooking"
    PAUSED = "paused"
    BASKET_OUT = "basket_out"
    HOLD = "hold"
    UNKNOWN = "unknown"


ACTIVE_STATUSES: Final = frozenset(
    {ZoneStatus.COOKING, ZoneStatus.PAUSED, ZoneStatus.BASKET_OUT, ZoneStatus.HOLD}
)
STARTABLE_STATUSES: Final = frozenset({ZoneStatus.STANDBY, ZoneStatus.READY})

# pyvesync AirFryerCookStatus value -> ZoneStatus
PYVESYNC_STATUS_MAP: Final[dict[str, ZoneStatus]] = {
    "standby": ZoneStatus.STANDBY,
    "ready": ZoneStatus.READY,
    "cooking": ZoneStatus.COOKING,
    "heating": ZoneStatus.COOKING,
    "cookStop": ZoneStatus.PAUSED,
    "preheatStop": ZoneStatus.PAUSED,
    "pullOut": ZoneStatus.BASKET_OUT,
    "hold": ZoneStatus.HOLD,
    "cookEnd": ZoneStatus.STANDBY,
}


class DeviceStatus(StrEnum):
    """Combined status of the fryer."""

    OFFLINE = "offline"
    IDLE = "idle"
    READY = "ready"
    COOKING = "cooking"
    PAUSED = "paused"


class SyncMode(StrEnum):
    """Reported syncType."""

    OFF = "off"
    MATCH = "match"
    SYNC = "sync"


SYNC_TYPE_MAP: Final[dict[int, SyncMode]] = {
    0: SyncMode.OFF,
    1: SyncMode.MATCH,
    2: SyncMode.SYNC,
}


class Program(StrEnum):
    """Cook programs of the TF101S (pyvesync api_mode values, lower-cased)."""

    AIRFRY = "airfry"
    ROAST = "roast"
    BAKE = "bake"
    GRILL = "grill"
    REHEAT = "reheat"
    DRY = "dry"


# Program key -> pyvesync api_mode string
PROGRAM_API_MODE: Final[dict[Program, str]] = {
    Program.AIRFRY: "AirFry",
    Program.ROAST: "Roast",
    Program.BAKE: "Bake",
    Program.GRILL: "Grill",
    Program.REHEAT: "Reheat",
    Program.DRY: "Dry",
}

# Maximum cook time in minutes the integration accepts per program. pyvesync
# does not check an upper limit; the fryer refuses what it does not accept and
# that refusal is reported. Dry defaults to 6 hours in the app.
PROGRAM_MAX_MINUTES: Final[dict[Program, int]] = {
    Program.AIRFRY: 60,
    Program.ROAST: 60,
    Program.BAKE: 60,
    Program.GRILL: 60,
    Program.REHEAT: 60,
    Program.DRY: 720,
}


class StartOutcome(StrEnum):
    """Result of the last start command."""

    NONE = "none"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


class ZoneEvent(StrEnum):
    """Event types fired per zone."""

    STARTED = "started"
    READY = "ready"
    PAUSED = "paused"
    RESUMED = "resumed"
    FINISHED = "finished"
    STOPPED = "stopped"
