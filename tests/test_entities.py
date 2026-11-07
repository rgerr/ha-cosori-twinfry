"""Entities, services and diagnostics."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest

from custom_components.cosori_twinfry.const import DOMAIN
from custom_components.cosori_twinfry.diagnostics import async_get_config_entry_diagnostics

from .conftest import setup_entry
from .simulator import CID, Chamber, FakeCloud

pytestmark = pytest.mark.usefixtures("patch_manager")


def _device(hass: HomeAssistant) -> dr.DeviceEntry:
    (device,) = dr.async_get(hass).async_get_devices(identifiers={(DOMAIN, CID)})
    return device


async def test_entity_set(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    ids = sorted(e.entity_id for e in entities)
    for zone in (1, 2):
        for expected in (
            f"sensor.twinfry_zone_{zone}_status",
            f"sensor.twinfry_zone_{zone}_program",
            f"sensor.twinfry_zone_{zone}_set_temperature",
            f"sensor.twinfry_zone_{zone}_set_time",
            f"sensor.twinfry_zone_{zone}_remaining_time",
            f"sensor.twinfry_zone_{zone}_ready_at",
            f"binary_sensor.twinfry_zone_{zone}_cooking",
            f"button.twinfry_start_zone_{zone}",
            f"button.twinfry_stop_zone_{zone}",
            f"number.twinfry_zone_{zone}_temperature",
            f"number.twinfry_zone_{zone}_cook_time",
            f"select.twinfry_zone_{zone}_program_choice",
            f"event.twinfry_zone_{zone}_event",
        ):
            assert expected in ids, expected
    for expected in (
        "button.twinfry_start_both_zones",
        "button.twinfry_stop_both_zones",
        "button.twinfry_match_start_zone_1_settings_in_both",
        "sensor.twinfry_status",
        "sensor.twinfry_sync_mode",
        "sensor.twinfry_last_start",
        "binary_sensor.twinfry_online",
    ):
        assert expected in ids, expected
    # No "current temperature" entity: the fryer does not report one.
    assert not any("current_temperature" in i for i in ids)
    device = _device(hass)
    assert device.manufacturer == "COSORI"
    assert device.model == "Dual Blaze TwinFry 10L"
    assert device.model_id == "CAF-TF101S-AEU"


async def test_sensor_units_and_classes(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.chambers[1] = Chamber(
        status="cooking", mode="Grill", set_time=600, temp=240, remaining=420
    )
    await setup_entry(hass)
    temp = hass.states.get("sensor.twinfry_zone_1_set_temperature")
    assert temp.state == "240"
    assert temp.attributes["unit_of_measurement"] == "°C"
    assert temp.attributes["device_class"] == "temperature"
    remaining = hass.states.get("sensor.twinfry_zone_1_remaining_time")
    assert float(remaining.state) == 7
    assert remaining.attributes["unit_of_measurement"] == "min"
    assert (
        hass.states.get("sensor.twinfry_zone_1_ready_at").attributes["device_class"] == "timestamp"
    )
    # Idle zone: no leftover values.
    assert hass.states.get("sensor.twinfry_zone_2_set_temperature").state == "unknown"
    assert hass.states.get("sensor.twinfry_zone_2_ready_at").state == "unknown"


async def test_program_select_loads_defaults(hass: HomeAssistant) -> None:
    await setup_entry(hass)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.twinfry_zone_2_program_choice", "option": "dry"},
        blocking=True,
    )
    temp = hass.states.get("number.twinfry_zone_2_temperature")
    assert temp.state == "55"
    assert temp.attributes["min"] == 35 and temp.attributes["max"] == 95
    assert hass.states.get("number.twinfry_zone_2_cook_time").state == "360"


async def test_number_validation(hass: HomeAssistant) -> None:
    await setup_entry(hass)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.twinfry_zone_1_temperature", "value": 180},
        blocking=True,
    )
    assert hass.states.get("number.twinfry_zone_1_temperature").state == "180"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.twinfry_zone_1_cook_time", "value": 61},
            blocking=True,
        )


async def test_settings_survive_reload(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)
    entry.runtime_data.controller.async_set_minutes(1, 33)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("number.twinfry_zone_1_cook_time").state == "33"


async def test_start_and_stop_buttons(hass: HomeAssistant, cloud: FakeCloud) -> None:
    await setup_entry(hass)
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.twinfry_start_zone_2"}, blocking=True
    )
    assert cloud.chambers[2].status == "cooking"
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.twinfry_stop_zone_2"}, blocking=True
    )
    assert cloud.chambers[2].status == "standby"


async def test_failed_start_button_raises(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.native_behaviour = "ignore"
    await setup_entry(hass)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.twinfry_start_zone_1"}, blocking=True
        )
    assert hass.states.get("sensor.twinfry_last_start").state == "failed"


async def test_start_cook_service(hass: HomeAssistant, cloud: FakeCloud) -> None:
    await setup_entry(hass)
    device = _device(hass)
    response = await hass.services.async_call(
        DOMAIN,
        "start_cook",
        {
            "device_id": device.id,
            "zone": "zone_1",
            "program": "bake",
            "temperature": 170,
            "duration": 30,
        },
        blocking=True,
        return_response=True,
    )
    assert response["started"] is True
    assert response["method"] == "native"
    (data,) = cloud.sent("startMultiCook")
    config = data["cookConfigs"][0]
    assert (config["mode"], config["cookTemp"], config["cookSetTime"]) == ("Bake", 170, 1800)

    await hass.services.async_call(
        DOMAIN, "stop_cook", {"device_id": device.id, "zone": "both"}, blocking=True
    )
    assert cloud.chambers[1].status == "standby"


async def test_service_unknown_device(hass: HomeAssistant) -> None:
    await setup_entry(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "stop_cook", {"device_id": "nope", "zone": "both"}, blocking=True
        )


async def test_diagnostics_have_no_secrets(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = json.dumps(diag, default=str)
    for secret in ("secret-password", "user@example.com", "token-secret", "acct-0001", CID):
        assert secret not in text
    assert diag["pyvesync_version"].startswith("3.5")
    assert diag["ready_start_route_available"] is True


DUTCH_IDS = (
    "sensor.twinfry_status",
    "sensor.twinfry_zone_1_status",
    "sensor.twinfry_zone_1_programma",
    "sensor.twinfry_zone_1_ingestelde_temperatuur",
    "sensor.twinfry_zone_1_ingestelde_tijd",
    "sensor.twinfry_zone_1_resterende_tijd",
    "sensor.twinfry_zone_1_klaar_om",
    "sensor.twinfry_laatste_start",
    "sensor.twinfry_laatste_geslaagde_update",
    "sensor.twinfry_sync_modus",
    "binary_sensor.twinfry_zone_1_kookt",
    "binary_sensor.twinfry_online",
    "button.twinfry_start_zone_1",
    "button.twinfry_stop_zone_2",
    "button.twinfry_start_beide_zones",
    "button.twinfry_stop_beide_zones",
    "button.twinfry_match_start_zone_1_in_beide",
    "number.twinfry_zone_2_temperatuur",
    "number.twinfry_zone_2_kooktijd",
    "select.twinfry_zone_2_programmakeuze",
    "event.twinfry_zone_2_gebeurtenis",
)


async def test_dutch_entity_ids_used_by_dashboard(hass: HomeAssistant) -> None:
    """The example dashboard relies on these ids (system language nl)."""
    hass.config.language = "nl"
    entry = await setup_entry(hass)
    ids = {
        e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    missing = [i for i in DUTCH_IDS if i not in ids]
    assert not missing, (missing, sorted(ids))
