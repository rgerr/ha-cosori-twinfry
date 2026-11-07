"""Tests of the pyvesync layer against pyvesync's real device classes."""

from __future__ import annotations

import pytest
from pyvesync.const import AirFryerChamber

from custom_components.cosori_twinfry.client import async_login_and_discover
from custom_components.cosori_twinfry.const import Program
from custom_components.cosori_twinfry.fryer_ext import (
    InvalidSettingsError,
    async_send_start,
    build_recipe,
    check_compatible,
    default_settings,
    last_error,
    last_poll_inner_result,
    supported_programs,
    temp_limits,
)

from .simulator import ACCOUNT_ID, DEVICE_TYPE, FakeCloud, FakeVeSync


async def _device(cloud: FakeCloud):
    manager = FakeVeSync(username="u", password="p", country_code="NL")
    manager.cloud = cloud
    fryers = await async_login_and_discover(manager)
    assert len(fryers) == 1
    return fryers[0]


async def test_discovery_uses_dual_fryer_class() -> None:
    device = await _device(FakeCloud())
    assert type(device).__name__ == "VeSyncDualAirFryer"
    assert device.device_type == DEVICE_TYPE
    assert check_compatible(device)
    assert AirFryerChamber.CHAMBER_2 in device.supported_chambers


async def test_aeur_model_number_is_recognised() -> None:
    cloud = FakeCloud()
    item = cloud.device_item()
    item["deviceType"] = "CAF-TF101S-AEUR"
    cloud.devices = [item]
    device = await _device(cloud)
    assert type(device).__name__ == "VeSyncDualAirFryer"


async def test_programs_limits_and_defaults() -> None:
    device = await _device(FakeCloud())
    assert supported_programs(device) == list(Program)
    assert temp_limits(device, Program.GRILL) == (205, 240, 5)
    assert temp_limits(device, Program.DRY) == (35, 95, 5)
    assert default_settings(device, Program.AIRFRY) == (200, 20)
    assert default_settings(device, Program.DRY) == (55, 360)


async def test_build_recipe_validates() -> None:
    device = await _device(FakeCloud())
    recipe = build_recipe(device, Program.AIRFRY, 183, 12)
    assert recipe.target_temp == 185  # rounded to the 5 °C step
    assert recipe.cook_time == 720
    assert recipe.cook_mode == "AirFry"
    with pytest.raises(InvalidSettingsError) as err:
        build_recipe(device, Program.AIRFRY, 240, 10)
    assert err.value.key == "temperature_out_of_range"
    with pytest.raises(InvalidSettingsError) as err:
        build_recipe(device, Program.AIRFRY, 200, 61)
    assert err.value.key == "time_out_of_range"
    with pytest.raises(InvalidSettingsError):
        build_recipe(device, Program.AIRFRY, 200, 0)


async def test_native_start_request_shape() -> None:
    cloud = FakeCloud()
    device = await _device(cloud)
    recipe = build_recipe(device, Program.ROAST, 190, 25)
    assert await async_send_start(device, recipe, AirFryerChamber.CHAMBER_2, ready_start=False)
    (data,) = cloud.sent("startMultiCook")
    assert data == {
        "accountId": ACCOUNT_ID,
        "cookConfigs": [
            {
                "chamber": 2,
                "cookSetTime": 1500,
                "cookTemp": 190,
                "mode": "Roast",
                "recipeId": 13,
                "recipeName": "Roast",
                "recipeType": 3,
            }
        ],
        "readyStart": False,
        "syncType": 0,
        "tempUnit": "c",
        "workChamber": 2,
    }


async def test_ready_start_request_differs_only_in_ready_start() -> None:
    cloud = FakeCloud()
    device = await _device(cloud)
    recipe = build_recipe(device, Program.ROAST, 190, 25)
    await async_send_start(device, recipe, AirFryerChamber.CHAMBER_2, ready_start=False)
    await async_send_start(device, recipe, AirFryerChamber.CHAMBER_2, ready_start=True)
    native, ready = cloud.sent("startMultiCook")
    assert ready.pop("readyStart") is True
    assert native.pop("readyStart") is False
    assert native == ready


async def test_match_start_sends_both_chambers_sync() -> None:
    cloud = FakeCloud()
    device = await _device(cloud)
    recipe = build_recipe(device, Program.AIRFRY, 200, 15)
    await async_send_start(device, recipe, AirFryerChamber.BOTH, ready_start=True)
    (data,) = cloud.sent("startMultiCook")
    assert data["workChamber"] == 4
    assert data["syncType"] == 2
    assert [c["chamber"] for c in data["cookConfigs"]] == [1, 2]


async def test_rejected_start_reports_reason() -> None:
    cloud = FakeCloud(reject_start_code=11910000)
    device = await _device(cloud)
    recipe = build_recipe(device, Program.AIRFRY, 200, 15)
    assert not await async_send_start(device, recipe, AirFryerChamber.CHAMBER_1, ready_start=False)
    assert "LEFT_ZONE_COOKING" in last_error(device)
    assert not await async_send_start(device, recipe, AirFryerChamber.CHAMBER_1, ready_start=True)


async def test_ready_start_without_helpers_is_refused() -> None:
    device = await _device(FakeCloud())

    class Crippled:
        def __getattr__(self, name):
            if name == "_prepare_recipe":
                raise AttributeError(name)
            return getattr(device, name)

    crippled = Crippled()
    assert not check_compatible(crippled)
    recipe = build_recipe(device, Program.AIRFRY, 200, 15)
    assert not await async_send_start(crippled, recipe, AirFryerChamber.CHAMBER_1, ready_start=True)


async def test_poll_inner_result() -> None:
    cloud = FakeCloud()
    device = await _device(cloud)
    await device.update()
    inner = last_poll_inner_result(device)
    assert inner is not None and "statusList" in inner
    cloud.online = False
    await device.update()
    assert last_poll_inner_result(device) is None
