"""The COSORI TwinFry integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from pyvesync.utils.errors import VeSyncError, VeSyncLoginError, VeSyncTokenError

from .client import async_login_and_discover, create_manager
from .const import CONF_COUNTRY_CODE, CONF_DEVICE_CID, DOMAIN
from .controller import TwinFryController
from .coordinator import TwinFryCoordinator
from .fryer_ext import check_compatible
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class TwinFryData:
    """Runtime data of a config entry."""

    coordinator: TwinFryCoordinator
    controller: TwinFryController


type TwinFryConfigEntry = ConfigEntry[TwinFryData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration services."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TwinFryConfigEntry) -> bool:
    """Set up a TwinFry from a config entry."""
    manager = create_manager(
        hass,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_COUNTRY_CODE, "NL"),
    )
    try:
        fryers = await async_login_and_discover(manager)
    except (VeSyncLoginError, VeSyncTokenError) as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="auth_failed"
        ) from err
    except (VeSyncError, aiohttp.ClientError, TimeoutError) as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"error": type(err).__name__},
        ) from err

    cid = entry.data[CONF_DEVICE_CID]
    device = next((dev for dev in fryers if dev.cid == cid), None)
    if device is None:
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="device_not_found")
    if not check_compatible(device):
        _LOGGER.warning(
            "This pyvesync version lacks helpers used by the SwitchBot start route; "
            "native start, stop and monitoring still work"
        )

    coordinator = TwinFryCoordinator(hass, entry, manager, device)
    await coordinator.async_config_entry_first_refresh()

    controller = TwinFryController(hass, entry, coordinator)
    await controller.async_load()

    entry.runtime_data = TwinFryData(coordinator=coordinator, controller=controller)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: TwinFryConfigEntry) -> None:
    """Reload when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TwinFryConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.controller.async_unload()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
