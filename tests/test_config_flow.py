"""Config, reauth and options flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.cosori_twinfry.const import (
    CONF_CONFIRM_TIMEOUT,
    CONF_COUNTRY_CODE,
    CONF_DEVICE_CID,
    CONF_PRESS_DELAY,
    CONF_READY_TIMEOUT,
    CONF_SCAN_INTERVAL_ACTIVE,
    CONF_SCAN_INTERVAL_IDLE,
    CONF_START_METHOD,
    CONF_SWITCHBOT_ENTITY,
    DOMAIN,
)

from .conftest import make_entry, setup_entry
from .simulator import CID, FakeCloud

pytestmark = pytest.mark.usefixtures("patch_manager")

USER_INPUT = {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "pw", CONF_COUNTRY_CODE: "nl"}


async def test_user_flow_single_device(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "TwinFry"
    assert result["data"] == {
        CONF_USERNAME: "user@example.com",
        CONF_PASSWORD: "pw",
        CONF_COUNTRY_CODE: "NL",
        CONF_DEVICE_CID: CID,
    }
    assert result["result"].unique_id == CID


async def test_user_flow_multiple_devices(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.devices = [cloud.device_item(), cloud.device_item(cid="second-cid", name="Kitchen")]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["step_id"] == "device"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_CID: "second-cid"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kitchen"


@pytest.mark.parametrize(
    ("setup", "error"),
    [
        (lambda c: setattr(c, "reject_login", True), "invalid_auth"),
        (lambda c: setattr(c, "devices", []), "no_devices"),
    ],
)
async def test_user_flow_errors(hass: HomeAssistant, cloud: FakeCloud, setup, error) -> None:
    setup(cloud)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_already_configured(hass: HomeAssistant) -> None:
    make_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = await setup_entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    cloud.reject_login = True
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "x"})
    assert result["errors"] == {"base": "invalid_auth"}
    cloud.reject_login = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-password"


OPTIONS = {
    CONF_PRESS_DELAY: 2,
    CONF_READY_TIMEOUT: 20,
    CONF_CONFIRM_TIMEOUT: 45,
    CONF_SCAN_INTERVAL_ACTIVE: 15,
    CONF_SCAN_INTERVAL_IDLE: 60,
}


async def test_options_switchbot_required(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**OPTIONS, CONF_START_METHOD: "switchbot"}
    )
    assert result["errors"] == {CONF_SWITCHBOT_ENTITY: "switchbot_required"}


async def test_options_switch_mode_refused(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.bot", "off", {"switch_mode": True})
    entry = await setup_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**OPTIONS, CONF_START_METHOD: "switchbot", CONF_SWITCHBOT_ENTITY: "switch.bot"},
    )
    assert result["errors"] == {CONF_SWITCHBOT_ENTITY: "switchbot_switch_mode"}


async def test_options_saved(hass: HomeAssistant) -> None:
    hass.states.async_set("button.bot", "unknown")
    entry = await setup_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**OPTIONS, CONF_START_METHOD: "auto", CONF_SWITCHBOT_ENTITY: "button.bot"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_START_METHOD] == "auto"
    assert entry.options[CONF_SWITCHBOT_ENTITY] == "button.bot"
    assert entry.runtime_data.controller.start_method == "auto"
