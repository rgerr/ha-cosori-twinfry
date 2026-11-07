"""Start/stop orchestration: native, SwitchBot, automatic, and the safety rules."""

from __future__ import annotations

import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest

from custom_components.cosori_twinfry.const import (
    CONF_START_METHOD,
    CONF_SWITCHBOT_ENTITY,
    Program,
    StartMethod,
    StartOutcome,
    Zone,
)

from .conftest import FakeBot, setup_entry
from .simulator import Chamber, FakeCloud

pytestmark = pytest.mark.usefixtures("patch_manager")

SWITCHBOT = {CONF_START_METHOD: StartMethod.SWITCHBOT, CONF_SWITCHBOT_ENTITY: "button.airfryer_bot"}
AUTO = {CONF_START_METHOD: StartMethod.AUTO, CONF_SWITCHBOT_ENTITY: "button.airfryer_bot"}


async def _controller(hass: HomeAssistant, options=None):
    entry = await setup_entry(hass, options)
    return entry.runtime_data.controller


def _key(err: pytest.ExceptionInfo) -> str:
    return err.value.translation_key


# ------------------------------------------------------------------ native


async def test_native_start_confirmed(hass: HomeAssistant, cloud: FakeCloud) -> None:
    controller = await _controller(hass)
    controller.async_set_program(1, Program.GRILL)
    assert await controller.async_start(Zone.ZONE_1) == "native"
    assert cloud.chambers[1].status == "cooking"
    assert cloud.sent("startMultiCook")[0]["readyStart"] is False
    assert controller.report.outcome == StartOutcome.SUCCESS
    assert "chamber_1_cooking_confirmed" in controller.report.steps
    await hass.async_block_till_done()
    assert hass.states.get("sensor.twinfry_zone_1_status").state == "cooking"
    assert hass.states.get("sensor.twinfry_last_start").state == "success"


async def test_api_success_alone_is_not_a_start(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """The API accepts the command but the fryer does nothing."""
    cloud.native_behaviour = "ignore"
    controller = await _controller(hass)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_1)
    assert _key(err) == "start_not_confirmed"
    assert controller.report.outcome == StartOutcome.FAILED
    await hass.async_block_till_done()
    # No optimistic "cooking" anywhere.
    assert hass.states.get("sensor.twinfry_zone_1_status").state == "standby"
    assert hass.states.get("binary_sensor.twinfry_zone_1_cooking").state == "off"


async def test_native_waiting_for_button(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.native_behaviour = "ready"
    controller = await _controller(hass)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_1)
    assert _key(err) == "waiting_for_button"
    await hass.async_block_till_done()
    assert hass.states.get("sensor.twinfry_zone_1_status").state == "ready"


async def test_native_rejected(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.reject_start_code = 11910000
    controller = await _controller(hass)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_1)
    assert _key(err) == "command_rejected"
    assert "LEFT_ZONE_COOKING" in err.value.translation_placeholders["error"]


async def test_busy_zone_is_not_restarted(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.chambers[1] = Chamber(
        status="cooking", mode="AirFry", set_time=600, temp=200, remaining=500
    )
    controller = await _controller(hass)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_1)
    assert _key(err) == "zone_busy"
    assert cloud.sent("startMultiCook") == []


async def test_concurrent_start_refused(hass: HomeAssistant, cloud: FakeCloud) -> None:
    controller = await _controller(hass)
    first = asyncio.create_task(controller.async_start(Zone.ZONE_1))
    await asyncio.sleep(0)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_1)
    assert _key(err) == "start_in_progress"
    assert await first == "native"
    assert len(cloud.sent("startMultiCook")) == 1


async def test_offline_fryer_is_not_started(hass: HomeAssistant, cloud: FakeCloud) -> None:
    controller = await _controller(hass)
    cloud.online = False
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_2)
    assert _key(err) == "device_offline"
    assert cloud.sent("startMultiCook") == []


async def test_unreachable_fryer_is_not_started(hass: HomeAssistant, cloud: FakeCloud) -> None:
    controller = await _controller(hass)
    cloud.fail_polls = 1
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_2)
    assert _key(err) == "not_reachable"
    assert cloud.sent("startMultiCook") == []


async def test_invalid_settings_rejected_before_sending(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    controller = await _controller(hass)
    with pytest.raises(ServiceValidationError):
        controller.async_set_temperature(1, 240)  # AirFry tops out at 205
    controller.settings[1].temperature = 240  # corrupt on purpose
    with pytest.raises(ServiceValidationError):
        await controller.async_start(Zone.ZONE_1)
    assert cloud.sent("startMultiCook") == []


async def test_both_independent_native(hass: HomeAssistant, cloud: FakeCloud) -> None:
    controller = await _controller(hass)
    controller.async_set_program(2, Program.BAKE)
    assert await controller.async_start(Zone.BOTH) == "native"
    first, second = cloud.sent("startMultiCook")
    assert (first["workChamber"], second["workChamber"]) == (1, 2)
    assert second["cookConfigs"][0]["mode"] == "Bake"
    assert cloud.chambers[1].status == cloud.chambers[2].status == "cooking"


async def test_match_start(hass: HomeAssistant, cloud: FakeCloud) -> None:
    controller = await _controller(hass)
    assert await controller.async_start(Zone.MATCH) == "native"
    (data,) = cloud.sent("startMultiCook")
    assert data["workChamber"] == 4
    assert data["syncType"] == 2
    await hass.async_block_till_done()
    assert hass.states.get("sensor.twinfry_sync_mode").state == "sync"


async def test_whole_basket_start(hass: HomeAssistant, cloud: FakeCloud) -> None:
    controller = await _controller(hass)
    assert await controller.async_start(Zone.WHOLE) == "native"
    assert cloud.sent("startMultiCook")[0]["workChamber"] == 3


# --------------------------------------------------------------- switchbot


async def test_switchbot_route(hass: HomeAssistant, cloud: FakeCloud, bot: FakeBot) -> None:
    controller = await _controller(hass, SWITCHBOT)
    assert await controller.async_start(Zone.ZONE_2) == "switchbot"
    (data,) = cloud.sent("startMultiCook")
    assert data["readyStart"] is True
    assert bot.presses == 1
    assert controller.report.steps[-3:] == [
        "chamber_2_ready_confirmed",
        "switchbot_pressed",
        "chamber_2_cooking_confirmed",
    ]


async def test_switchbot_not_pressed_without_ready(
    hass: HomeAssistant, cloud: FakeCloud, bot: FakeBot
) -> None:
    cloud.ready_behaviour = "ignore"
    controller = await _controller(hass, SWITCHBOT)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_1)
    assert _key(err) == "not_ready"
    assert bot.presses == 0


async def test_switchbot_press_without_effect(hass: HomeAssistant, cloud: FakeCloud) -> None:
    bot = FakeBot(hass, cloud, "button.airfryer_bot", effective=False)
    controller = await _controller(hass, SWITCHBOT)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_1)
    assert _key(err) == "not_confirmed_after_press"
    assert bot.presses == 1


async def test_switchbot_service_failure(hass: HomeAssistant, cloud: FakeCloud) -> None:
    FakeBot(hass, cloud, "button.airfryer_bot", fail=True)
    controller = await _controller(hass, SWITCHBOT)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_1)
    assert _key(err) == "switchbot_failed"


async def test_switchbot_unavailable_checked_first(hass: HomeAssistant, cloud: FakeCloud) -> None:
    hass.states.async_set("button.airfryer_bot", "unavailable")
    controller = await _controller(hass, SWITCHBOT)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_1)
    assert _key(err) == "switchbot_unavailable"
    assert cloud.sent("startMultiCook") == []


async def test_switch_bot_in_switch_mode_refused(hass: HomeAssistant, cloud: FakeCloud) -> None:
    FakeBot(hass, cloud, "switch.airfryer_bot", switch_mode=True)
    controller = await _controller(
        hass,
        {CONF_START_METHOD: StartMethod.SWITCHBOT, CONF_SWITCHBOT_ENTITY: "switch.airfryer_bot"},
    )
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_1)
    assert _key(err) == "switchbot_switch_mode"


async def test_switch_bot_press_mode(hass: HomeAssistant, cloud: FakeCloud) -> None:
    bot = FakeBot(hass, cloud, "switch.airfryer_bot")
    controller = await _controller(
        hass,
        {CONF_START_METHOD: StartMethod.SWITCHBOT, CONF_SWITCHBOT_ENTITY: "switch.airfryer_bot"},
    )
    assert await controller.async_start(Zone.ZONE_1) == "switchbot"
    assert bot.presses == 1


async def test_switchbot_never_presses_while_other_zone_runs(
    hass: HomeAssistant, cloud: FakeCloud, bot: FakeBot
) -> None:
    cloud.chambers[1] = Chamber(
        status="cooking", mode="AirFry", set_time=600, temp=200, remaining=500
    )
    controller = await _controller(hass, SWITCHBOT)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_2)
    assert _key(err) == "other_zone_active"
    assert bot.presses == 0
    assert cloud.sent("startMultiCook") == []


async def test_switchbot_both_needs_equal_settings(
    hass: HomeAssistant, cloud: FakeCloud, bot: FakeBot
) -> None:
    controller = await _controller(hass, SWITCHBOT)
    controller.async_set_program(2, Program.BAKE)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.BOTH)
    assert _key(err) == "both_needs_equal_settings"
    # Equal settings: one combined program, one press.
    controller.async_set_program(2, Program.AIRFRY)
    assert await controller.async_start(Zone.BOTH) == "switchbot"
    assert bot.presses == 1
    assert cloud.sent("startMultiCook")[-1]["workChamber"] == 4


# -------------------------------------------------------------------- auto


async def test_auto_native_works(hass: HomeAssistant, cloud: FakeCloud, bot: FakeBot) -> None:
    controller = await _controller(hass, AUTO)
    assert await controller.async_start(Zone.ZONE_1) == "native"
    assert bot.presses == 0


async def test_auto_presses_when_fryer_waits(
    hass: HomeAssistant, cloud: FakeCloud, bot: FakeBot
) -> None:
    cloud.native_behaviour = "ready"
    controller = await _controller(hass, AUTO)
    assert await controller.async_start(Zone.ZONE_1) == "switchbot"
    assert bot.presses == 1
    # The loaded program was pressed; no second program was sent.
    assert len(cloud.sent("startMultiCook")) == 1


async def test_auto_falls_back_when_native_ignored(
    hass: HomeAssistant, cloud: FakeCloud, bot: FakeBot
) -> None:
    cloud.native_behaviour = "ignore"
    controller = await _controller(hass, AUTO)
    assert await controller.async_start(Zone.ZONE_1) == "switchbot"
    native, ready = cloud.sent("startMultiCook")
    assert (native["readyStart"], ready["readyStart"]) == (False, True)
    assert bot.presses == 1


async def test_auto_without_switchbot_is_native(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.native_behaviour = "ready"
    controller = await _controller(hass, {CONF_START_METHOD: StartMethod.AUTO})
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_start(Zone.ZONE_1)
    assert _key(err) == "waiting_for_button"


# -------------------------------------------------------------------- stop


async def test_stop_zone_confirmed(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.chambers[2] = Chamber(
        status="cooking", mode="AirFry", set_time=600, temp=200, remaining=500
    )
    controller = await _controller(hass)
    await controller.async_stop(Zone.ZONE_2)
    assert cloud.sent("endCook") == [{"chamber": 2}]
    assert cloud.chambers[2].status == "standby"


async def test_stop_both_only_stops_active(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.chambers[1] = Chamber(
        status="ready", mode="AirFry", set_time=600, temp=200, remaining=600
    )
    controller = await _controller(hass)
    await controller.async_stop(Zone.BOTH)
    assert cloud.sent("endCook") == [{"chamber": 1}]


async def test_stop_idle_sends_nothing(hass: HomeAssistant, cloud: FakeCloud) -> None:
    controller = await _controller(hass)
    await controller.async_stop(Zone.BOTH)
    assert cloud.sent("endCook") == []


async def test_stop_whole_basket(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.work_chamber = 3
    cloud.chambers[3] = Chamber(
        status="cooking", mode="Roast", set_time=1800, temp=190, remaining=1700
    )
    controller = await _controller(hass)
    await controller.async_stop(Zone.ZONE_1)
    assert cloud.sent("endCook") == [{"chamber": 3}]


async def test_stop_not_blocked_by_running_start(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.native_behaviour = "ignore"
    controller = await _controller(hass)
    controller.entry  # noqa: B018
    start = asyncio.create_task(controller.async_start(Zone.ZONE_1))
    await asyncio.sleep(0)
    cloud.chambers[2] = Chamber(
        status="cooking", mode="AirFry", set_time=600, temp=200, remaining=500
    )
    await controller.async_stop(Zone.ZONE_2)
    assert cloud.chambers[2].status == "standby"
    with pytest.raises(HomeAssistantError):
        await start
