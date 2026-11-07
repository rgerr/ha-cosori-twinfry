"""VeSync account helpers (single place that creates the pyvesync manager)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pyvesync import VeSync
from pyvesync.utils.errors import VeSyncLoginError

from .const import API_TIMEOUT

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pyvesync.devices.vesynckitchen import VeSyncDualAirFryer


def create_manager(hass: HomeAssistant, username: str, password: str, country_code: str) -> VeSync:
    """Create a pyvesync manager using Home Assistant's HTTP session."""
    return VeSync(
        username=username,
        password=password,
        country_code=country_code.upper(),
        session=async_get_clientsession(hass),
        time_zone=str(hass.config.time_zone),
        redact=True,
    )


async def async_login_and_discover(manager: VeSync) -> list[VeSyncDualAirFryer]:
    """Log in, fetch the device list and return the dual-chamber fryers.

    Raises the pyvesync errors (VeSyncLoginError, VeSyncServerError, ...)
    and TimeoutError unchanged; the callers map them.
    """
    async with asyncio.timeout(API_TIMEOUT):
        if not await manager.login():
            raise VeSyncLoginError("VeSync login was not accepted")
    async with asyncio.timeout(API_TIMEOUT):
        await manager.get_devices()
    return [
        dev
        for dev in manager.devices.air_fryers
        if getattr(dev, "is_dual_chamber", False) and hasattr(dev, "state_chamber_2")
    ]
