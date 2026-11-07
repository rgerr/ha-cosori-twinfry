"""Services of the COSORI TwinFry integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:  # Home Assistant 2026.10+ validates with probatio
    import probatio as vol
except ImportError:  # pragma: no cover - older Home Assistant
    import voluptuous as vol  # type: ignore[no-redef]

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import DOMAIN, Program, StartMethod, Zone

if TYPE_CHECKING:
    from .controller import TwinFryController

SERVICE_START_COOK = "start_cook"
SERVICE_STOP_COOK = "stop_cook"

ATTR_ZONE = "zone"
ATTR_PROGRAM = "program"
ATTR_TEMPERATURE = "temperature"
ATTR_DURATION = "duration"
ATTR_METHOD = "method"

START_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_ZONE): vol.In([z.value for z in Zone]),
        vol.Optional(ATTR_PROGRAM): vol.In([p.value for p in Program]),
        vol.Optional(ATTR_TEMPERATURE): vol.All(vol.Coerce(int), vol.Range(min=30, max=250)),
        vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Range(min=1, max=720)),
        vol.Optional(ATTR_METHOD): vol.In([m.value for m in StartMethod]),
    }
)

STOP_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_ZONE): vol.In([Zone.ZONE_1.value, Zone.ZONE_2.value, Zone.BOTH.value]),
    }
)


def _controller(hass: HomeAssistant, device_id: str) -> TwinFryController:
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="unknown_device")
    entry_ids = (
        [device.config_entry_id]  # HA 2026.10+: a device has one config entry
        if hasattr(device, "config_entry_id")
        else list(device.config_entries)  # pragma: no cover - older Home Assistant
    )
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and entry.domain == DOMAIN:
            if entry.state is not ConfigEntryState.LOADED:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="entry_not_loaded"
                )
            return entry.runtime_data.controller
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="unknown_device")


async def _async_start_cook(call: ServiceCall) -> ServiceResponse:
    controller = _controller(call.hass, call.data[ATTR_DEVICE_ID])
    target = Zone(call.data[ATTR_ZONE])
    zones = (2,) if target == Zone.ZONE_2 else (1,)
    if target == Zone.BOTH:
        zones = (1, 2)
    for zone in zones:
        if ATTR_PROGRAM in call.data:
            controller.async_set_program(zone, Program(call.data[ATTR_PROGRAM]))
        if ATTR_TEMPERATURE in call.data:
            controller.async_set_temperature(zone, call.data[ATTR_TEMPERATURE])
        if ATTR_DURATION in call.data:
            controller.async_set_minutes(zone, call.data[ATTR_DURATION])
    method = StartMethod(call.data[ATTR_METHOD]) if ATTR_METHOD in call.data else None
    used = await controller.async_start(target, method)
    return {"started": True, "method": used, "steps": controller.report.steps}


async def _async_stop_cook(call: ServiceCall) -> None:
    controller = _controller(call.hass, call.data[ATTR_DEVICE_ID])
    await controller.async_stop(Zone(call.data[ATTR_ZONE]))


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the services."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_START_COOK,
        _async_start_cook,
        schema=START_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_STOP_COOK, _async_stop_cook, schema=STOP_SCHEMA)
