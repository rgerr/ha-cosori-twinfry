"""Setup, polling and error handling."""

from __future__ import annotations

from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pyvesync.utils.errors import VeSyncServerError, VeSyncTokenError

from custom_components.cosori_twinfry.const import EVENT_TWINFRY

from .conftest import make_entry, setup_entry
from .simulator import Chamber, FakeCloud

pytestmark = pytest.mark.usefixtures("patch_manager")

STATUS_1 = "sensor.twinfry_zone_1_status"
STATUS_2 = "sensor.twinfry_zone_2_status"
DEVICE_STATUS = "sensor.twinfry_status"


async def _refresh(hass: HomeAssistant, entry) -> None:
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_setup_and_unload(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(STATUS_1).state == "standby"
    assert hass.states.get(DEVICE_STATUS).state == "idle"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_login_rejected_starts_reauth(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.reject_login = True
    entry = make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_device_missing_retries(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.devices = []
    entry = make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_restart_while_cooking_reads_real_state(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.chambers[2] = Chamber(
        status="cooking", mode="Bake", set_time=1500, temp=160, remaining=600
    )
    events = []
    hass.bus.async_listen(EVENT_TWINFRY, events.append)
    await setup_entry(hass)
    assert hass.states.get(STATUS_2).state == "cooking"
    assert hass.states.get("sensor.twinfry_zone_2_program").state == "bake"
    assert float(hass.states.get("sensor.twinfry_zone_2_remaining_time").state) == 10
    assert hass.states.get("binary_sensor.twinfry_zone_2_cooking").state == "on"
    # Already cooking at startup is not a "started" event.
    assert events == []


async def test_failed_poll_makes_entities_unavailable(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.chambers[1] = Chamber(
        status="cooking", mode="AirFry", set_time=1200, temp=200, remaining=900
    )
    entry = await setup_entry(hass)
    assert hass.states.get(STATUS_1).state == "cooking"

    cloud.fail_polls = 1  # unreadable response
    await _refresh(hass, entry)
    # No stale "cooking" shown as current.
    assert hass.states.get(STATUS_1).state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.twinfry_zone_1_remaining_time").state == STATE_UNAVAILABLE
    last_poll = hass.states.get("sensor.twinfry_last_successful_update")
    assert last_poll.attributes["last_poll_successful"] is False

    await _refresh(hass, entry)
    assert hass.states.get(STATUS_1).state == "cooking"


@pytest.mark.parametrize(
    "exc", [VeSyncServerError("boom"), aiohttp.ClientError("no internet"), TimeoutError()]
)
async def test_network_errors_are_update_failed(
    hass: HomeAssistant, cloud: FakeCloud, exc: Exception
) -> None:
    entry = await setup_entry(hass)
    cloud.poll_exception = exc
    await _refresh(hass, entry)
    assert not entry.runtime_data.coordinator.last_update_success
    assert hass.states.get(STATUS_1).state == STATE_UNAVAILABLE
    cloud.poll_exception = None
    await _refresh(hass, entry)
    assert hass.states.get(STATUS_1).state == "standby"


async def test_token_error_starts_reauth(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = await setup_entry(hass)
    cloud.poll_exception = VeSyncTokenError("expired")
    await _refresh(hass, entry)
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_offline_fryer(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = await setup_entry(hass)
    cloud.online = False
    await _refresh(hass, entry)
    assert hass.states.get(DEVICE_STATUS).state == "offline"
    assert hass.states.get("binary_sensor.twinfry_online").state == "off"
    assert hass.states.get(STATUS_1).state == STATE_UNAVAILABLE


async def test_whole_basket_marks_zone_2_unavailable(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.work_chamber = 3
    cloud.chambers[3] = Chamber(
        status="cooking", mode="Roast", set_time=1800, temp=190, remaining=1700
    )
    await setup_entry(hass)
    assert hass.states.get(STATUS_1).state == "cooking"
    assert hass.states.get(STATUS_2).state == STATE_UNAVAILABLE
    assert hass.states.get(DEVICE_STATUS).attributes["whole_basket"] is True


async def test_events_finished_and_stopped(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.chambers[1] = Chamber(
        status="cooking", mode="AirFry", set_time=1200, temp=200, remaining=30
    )
    cloud.chambers[2] = Chamber(
        status="cooking", mode="AirFry", set_time=1200, temp=200, remaining=900
    )
    events = []
    hass.bus.async_listen(EVENT_TWINFRY, events.append)
    entry = await setup_entry(hass)

    cloud.finish(1)  # ran out
    cloud.chambers[2] = Chamber()  # ended early on the fryer
    await _refresh(hass, entry)

    by_zone = {e.data["zone"]: e.data["event"] for e in events}
    assert by_zone == {1: "finished", 2: "stopped"}
    event_state = hass.states.get("event.twinfry_zone_1_event")
    assert event_state.attributes["event_type"] == "finished"


async def test_poll_interval_follows_activity(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = await setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    assert coordinator.update_interval == timedelta(seconds=60)
    cloud.chambers[1] = Chamber(
        status="cooking", mode="AirFry", set_time=600, temp=200, remaining=600
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert coordinator.update_interval == timedelta(seconds=15)
