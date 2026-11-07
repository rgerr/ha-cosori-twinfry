"""Diagnostics for the COSORI TwinFry integration (no credentials or tokens)."""

from __future__ import annotations

from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_CID
from .fryer_ext import check_compatible, last_poll_inner_result

if TYPE_CHECKING:
    from . import TwinFryConfigEntry

TO_REDACT = {
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE_CID,
    "accountId",
    "accountID",
    "token",
    "cid",
    "uuid",
    "macID",
    "mac_id",
}


def _pyvesync_version() -> str:
    try:
        return version("pyvesync")
    except PackageNotFoundError:
        return "unknown"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TwinFryConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    coordinator, controller = data.coordinator, data.controller
    device = coordinator.device
    snapshot = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "pyvesync_version": _pyvesync_version(),
        "ready_start_route_available": check_compatible(device),
        "device": {
            "device_type": device.device_type,
            "config_module": getattr(device, "config_module", None),
            "firmware": getattr(device, "current_firm_version", None),
            "temp_unit": device.temp_unit.code,
            "supported_chambers": [int(c) for c in device.supported_chambers],
        },
        "last_poll_successful": coordinator.last_update_success,
        "last_error": coordinator.last_error,
        "snapshot": asdict(snapshot) if snapshot else None,
        "last_raw_status": async_redact_data(last_poll_inner_result(device) or {}, TO_REDACT),
        "staged_settings": {z: s.as_dict() for z, s in controller.settings.items()},
        "last_start": {
            "outcome": controller.report.outcome.value,
            **controller.report.as_dict(),
        },
    }
