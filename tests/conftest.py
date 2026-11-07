"""Fixtures for the COSORI TwinFry tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, ClassVar
from unittest.mock import patch

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cosori_twinfry.const import (
    CONF_CONFIRM_TIMEOUT,
    CONF_COUNTRY_CODE,
    CONF_DEVICE_CID,
    CONF_PRESS_DELAY,
    CONF_READY_TIMEOUT,
    DOMAIN,
)

from .simulator import CID, FakeCloud, FakeVeSync


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations."""


@pytest.fixture
def cloud() -> Generator[FakeCloud]:
    """The simulated VeSync cloud."""
    yield FakeCloud()
    FakeBot.instances.clear()


@pytest.fixture
def patch_manager(cloud: FakeCloud) -> Generator[None]:
    """Make the integration use the fake cloud."""

    def _factory(hass: HomeAssistant, username: str, password: str, country: str) -> FakeVeSync:
        manager = FakeVeSync(username=username, password=password, country_code=country)
        manager.cloud = cloud
        return manager

    with (
        patch("custom_components.cosori_twinfry.create_manager", _factory),
        patch("custom_components.cosori_twinfry.config_flow.create_manager", _factory),
    ):
        yield


FAST_OPTIONS = {
    CONF_PRESS_DELAY: 0,
    CONF_READY_TIMEOUT: 1,
    CONF_CONFIRM_TIMEOUT: 1,
}


def make_entry(options: dict[str, Any] | None = None) -> MockConfigEntry:
    """Build a config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="TwinFry",
        unique_id=CID,
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret-password",
            CONF_COUNTRY_CODE: "NL",
            CONF_DEVICE_CID: CID,
        },
        options={**FAST_OPTIONS, **(options or {})},
    )


async def setup_entry(
    hass: HomeAssistant, options: dict[str, Any] | None = None
) -> MockConfigEntry:
    """Set up the integration and make confirmation polls instant."""
    entry = make_entry(options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = entry.runtime_data.controller
    controller.confirm_poll_interval = 0
    # The integration's button platform registers the real button.press
    # service; put the fake Bot's handler back on top of it.
    for fake in FakeBot.instances:
        fake.register()
    return entry


class FakeBot:
    """A SwitchBot Bot exposed as button.press or switch.turn_on."""

    instances: ClassVar[list[FakeBot]] = []

    def __init__(
        self,
        hass: HomeAssistant,
        cloud: FakeCloud,
        entity_id: str,
        *,
        switch_mode: bool = False,
        fail: bool = False,
        effective: bool = True,
    ) -> None:
        self.presses = 0
        self.entity_id = entity_id
        self.cloud = cloud
        self.fail = fail
        self.effective = effective
        domain = entity_id.split(".", maxsplit=1)[0]
        attrs = {"switch_mode": switch_mode, "last_run_success": True} if domain == "switch" else {}
        hass.states.async_set(entity_id, "unknown" if domain == "button" else "off", attrs)
        self.hass = hass
        self.domain = domain
        FakeBot.instances.append(self)
        self.register()

    def register(self) -> None:
        service = "press" if self.domain == "button" else "turn_on"
        self.hass.services.async_register(self.domain, service, self._handle)

    async def _handle(self, call: ServiceCall) -> None:
        self.presses += 1
        if self.fail:
            from homeassistant.exceptions import HomeAssistantError  # noqa: PLC0415

            raise HomeAssistantError("bluetooth timeout")
        if self.effective:
            self.cloud.press_start_button()


@pytest.fixture
def bot(hass: HomeAssistant, cloud: FakeCloud) -> FakeBot:
    """A SwitchBot cloud-style button."""
    return FakeBot(hass, cloud, "button.airfryer_bot")
