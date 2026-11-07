"""Thin, isolated layer on top of pyvesync's ``VeSyncDualAirFryer``.

Why this module exists
----------------------
pyvesync 3.5.0 sends ``startMultiCook`` with ``readyStart: false`` only. With
``readyStart: true`` the fryer is meant to load the program and wait in the
``ready`` state for its physical start button; that is what the SwitchBot
start route needs. pyvesync has no public parameter for it, so
``async_send_start(..., ready_start=True)`` builds the same request with
pyvesync's own validation and request models, changing only ``readyStart``.

It uses three private pyvesync helpers (``_validate_chamber``,
``_prepare_recipe``, ``_build_cook_configs``, ``_get_sync_type``). That is why
the requirement is pinned to ``pyvesync>=3.5.0,<3.6`` and why
``check_compatible()`` runs at setup: a pyvesync change that removes them
disables only the SwitchBot route, never silently sends a different request.

Everything else (native start, stop, polling) uses pyvesync's public API.

Device type fallback
--------------------
pyvesync matches the ``deviceType`` the cloud reports against a fixed list,
dropping at most one trailing segment. Newer TwinFry variants such as the 2026
ceramic ``CAF-TF101S-AEUR-C`` have two segments after the model, so pyvesync
3.5.0 skips them. ``install_device_type_fallback()`` wraps the lookup pyvesync's
device container uses: only for types starting with ``CAF-TF101S`` or
``CAF-TF102S`` it drops trailing segments until the type resolves, and only
accepts a result that is the dual-chamber fryer class. Every other device
type resolves exactly as before.
"""

from __future__ import annotations

from dataclasses import replace
import logging
from typing import TYPE_CHECKING, Any

from pyvesync import device_container
from pyvesync.const import BYPASSV2_SUB_DEVICE_PAYLOAD, AirFryerChamber
from pyvesync.device_map import get_device_config
from pyvesync.models import fryer_models
from pyvesync.utils.helpers import Helpers

from .const import PROGRAM_API_MODE, PROGRAM_MAX_MINUTES, Program
from .models import minutes_to_seconds

if TYPE_CHECKING:
    from pyvesync.const import AirFryerPresetRecipe
    from pyvesync.devices.vesynckitchen import VeSyncDualAirFryer

_LOGGER = logging.getLogger(__name__)

_PRIVATE_HELPERS = (
    "_validate_chamber",
    "_prepare_recipe",
    "_build_cook_configs",
    "_get_sync_type",
    "call_bypassv2_api",
)


_DUAL_FRYER_CLASS = "VeSyncDualAirFryer"
_TWINFRY_PREFIXES = ("CAF-TF101S", "CAF-TF102S")


def resolve_device_config(device_type: str | None) -> Any:
    """Look up a device type, with a fallback for TwinFry variant suffixes."""
    config = get_device_config(device_type) if device_type else None
    if config is not None or not device_type:
        return config
    if not device_type.upper().startswith(_TWINFRY_PREFIXES):
        return None
    parts = device_type.split("-")
    for keep in range(len(parts) - 1, 1, -1):
        candidate = "-".join(parts[:keep])
        config = get_device_config(candidate)
        if config is not None and config.class_name == _DUAL_FRYER_CLASS:
            _LOGGER.debug("Device type %s handled as %s", device_type, candidate)
            return config
    return None


resolve_device_config.twinfry_fallback = True  # type: ignore[attr-defined]


def install_device_type_fallback() -> None:
    """Make pyvesync's device container use ``resolve_device_config`` (idempotent)."""
    if getattr(device_container.get_device_config, "twinfry_fallback", False):
        return
    device_container.get_device_config = resolve_device_config


class InvalidSettingsError(ValueError):
    """Raised when cook settings are not valid for the fryer."""

    def __init__(self, key: str, **placeholders: Any) -> None:
        """Store a translation key and placeholders."""
        super().__init__(key)
        self.key = key
        self.placeholders = {k: str(v) for k, v in placeholders.items()}


def check_compatible(device: Any) -> bool:
    """Return True if the private helpers the ready-start route needs exist."""
    return all(hasattr(device, name) for name in _PRIVATE_HELPERS)


def temp_limits(device: VeSyncDualAirFryer, program: Program) -> tuple[int, int, int]:
    """Return (min, max, step) for a program in the device's unit."""
    limits = device.temp_limits(PROGRAM_API_MODE[program])
    return limits.min_temp, limits.max_temp, limits.step


def default_settings(device: VeSyncDualAirFryer, program: Program) -> tuple[int, int]:
    """Return the app's default (temperature, minutes) for a program."""
    recipe = device.get_mode_recipe(PROGRAM_API_MODE[program])
    if recipe is None:
        raise InvalidSettingsError("program_not_supported", program=program.value)
    return int(recipe.target_temp), max(1, round(int(recipe.cook_time) / 60))


def supported_programs(device: VeSyncDualAirFryer) -> list[Program]:
    """Return the programs this fryer has (the TF102S has no Dry)."""
    return [p for p in Program if device.get_cook_mode(PROGRAM_API_MODE[p]) is not None]


def build_recipe(
    device: VeSyncDualAirFryer, program: Program, temperature: int, minutes: int
) -> AirFryerPresetRecipe:
    """Validate settings and return the recipe to send.

    Raises:
        InvalidSettingsError: program, temperature or time not accepted.
    """
    api_mode = PROGRAM_API_MODE[program]
    recipe = device.get_mode_recipe(api_mode)
    if recipe is None:
        raise InvalidSettingsError("program_not_supported", program=program.value)
    low, high, _step = temp_limits(device, program)
    prepared = device.prepare_temperature(int(temperature), api_mode)
    if prepared is None:
        raise InvalidSettingsError(
            "temperature_out_of_range",
            temperature=temperature,
            min=low,
            max=high,
            program=program.value,
        )
    max_minutes = PROGRAM_MAX_MINUTES[program]
    if not 1 <= int(minutes) <= max_minutes:
        raise InvalidSettingsError(
            "time_out_of_range", minutes=minutes, max=max_minutes, program=program.value
        )
    return replace(
        recipe,
        cook_time=minutes_to_seconds(minutes),
        target_temp=prepared,
        temp_unit=device.temp_unit.code,
        preheat_time=None,
    )


async def async_send_start(
    device: VeSyncDualAirFryer,
    recipe: AirFryerPresetRecipe,
    chamber: AirFryerChamber,
    *,
    ready_start: bool,
) -> bool:
    """Send ``startMultiCook``. Returns True when the API accepted it.

    An accepted request is NOT proof that the fryer started; the caller must
    confirm with a fresh poll.
    """
    if not ready_start:
        # Public pyvesync API (readyStart false).
        return bool(await device.set_mode_from_recipe(recipe, chamber=chamber))

    if not check_compatible(device):
        _LOGGER.error(
            "Installed pyvesync lacks the helpers for a ready-start request; "
            "the SwitchBot start route is unavailable"
        )
        return False
    member = device._validate_chamber(chamber)
    if member is None:
        return False
    prepared = device._prepare_recipe(recipe)
    if prepared is None:
        return False
    configs = device._build_cook_configs(prepared, member)
    data = fryer_models.FryerDualStartCookData.from_dict(
        {
            "accountId": device.manager.account_id,
            "cookConfigs": [c.to_dict() for c in configs],
            "readyStart": True,
            "syncType": int(device._get_sync_type(member)),
            "tempUnit": device.temp_unit.code,
            "workChamber": int(member),
        }
    )
    resp = await device.call_bypassv2_api(
        payload_method="startMultiCook",
        data=data.to_dict(),
        payload_update=dict(BYPASSV2_SUB_DEVICE_PAYLOAD),
    )
    # Deliberately no local state change: only a poll may say what happened.
    return Helpers.process_dev_response(_LOGGER, "start_ready", device, resp) is not None


def last_error(device: Any) -> str:
    """Return a readable reason from the last API response."""
    info = getattr(device, "last_response", None)
    if info is None:
        return "no response"
    name = getattr(info, "name", "") or ""
    message = getattr(info, "message", "") or ""
    if name and message:
        return f"{name}: {message}"
    return name or message or "unknown error"


def last_poll_inner_result(device: Any) -> dict[str, Any] | None:
    """Return the inner ``result`` of the last API response if it was a success."""
    info = getattr(device, "last_response", None)
    if info is None or getattr(info, "code", None) != 0:
        return None
    data = getattr(info, "response_data", None)
    if not isinstance(data, dict):
        return None
    outer = data.get("result")
    if not isinstance(outer, dict):
        return None
    inner = outer.get("result")
    return inner if isinstance(inner, dict) else None
