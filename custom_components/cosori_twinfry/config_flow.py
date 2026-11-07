"""Config and options flow for the COSORI TwinFry integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

try:  # Home Assistant 2026.10+ validates with probatio
    import probatio as vol
except ImportError:  # pragma: no cover - older Home Assistant
    import voluptuous as vol  # type: ignore[no-redef]

import aiohttp
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from pyvesync.utils.errors import VeSyncError, VeSyncLoginError, VeSyncTokenError

from .client import async_login_and_discover, create_manager
from .const import (
    CONF_CONFIRM_TIMEOUT,
    CONF_COUNTRY_CODE,
    CONF_DEVICE_CID,
    CONF_PRESS_DELAY,
    CONF_READY_TIMEOUT,
    CONF_SCAN_INTERVAL_ACTIVE,
    CONF_SCAN_INTERVAL_IDLE,
    CONF_START_METHOD,
    CONF_SWITCHBOT_ENTITY,
    DEFAULT_CONFIRM_TIMEOUT,
    DEFAULT_PRESS_DELAY,
    DEFAULT_READY_TIMEOUT,
    DEFAULT_SCAN_INTERVAL_ACTIVE,
    DEFAULT_SCAN_INTERVAL_IDLE,
    DOMAIN,
    SWITCHBOT_DOMAINS,
    StartMethod,
)

_LOGGER = logging.getLogger(__name__)


def _number(low: int, high: int, unit: str = "s") -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=low, max=high, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement=unit
        )
    )


async def _async_discover(
    flow: ConfigFlow, username: str, password: str, country: str
) -> tuple[dict[str, str], str | None]:
    """Log in and return ({cid: title}, error_key)."""
    manager = create_manager(flow.hass, username, password, country)
    try:
        fryers = await async_login_and_discover(manager)
    except (VeSyncLoginError, VeSyncTokenError):
        return {}, "invalid_auth"
    except (VeSyncError, aiohttp.ClientError, TimeoutError):
        return {}, "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error while logging in to VeSync")
        return {}, "unknown"
    if not fryers:
        return {}, "no_devices"
    return {dev.cid: f"{dev.device_name} ({dev.device_type})" for dev in fryers}, None


class TwinFryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._credentials: dict[str, str] = {}
        self._fryers: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the VeSync account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            country = str(user_input[CONF_COUNTRY_CODE]).strip().upper()
            fryers, error = await _async_discover(
                self, user_input[CONF_USERNAME], user_input[CONF_PASSWORD], country
            )
            if error:
                errors["base"] = error
            else:
                self._credentials = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_COUNTRY_CODE: country,
                }
                self._fryers = fryers
                if len(fryers) == 1:
                    return await self._async_create(next(iter(fryers)))
                return await self.async_step_device()

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.PASSWORD, autocomplete="current-password"
                    )
                ),
                vol.Required(
                    CONF_COUNTRY_CODE, default=(self.hass.config.country or "NL")
                ): TextSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose the fryer when the account has more than one."""
        if user_input is not None:
            return await self._async_create(user_input[CONF_DEVICE_CID])
        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_CID): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": cid, "label": title} for cid, title in self._fryers.items()
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="device", data_schema=schema)

    async def _async_create(self, cid: str) -> ConfigFlowResult:
        await self.async_set_unique_id(cid)
        self._abort_if_unique_id_configured()
        title = self._fryers.get(cid, "COSORI TwinFry").split(" (")[0]
        return self.async_create_entry(
            title=title, data={**self._credentials, CONF_DEVICE_CID: cid}
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            fryers, error = await _async_discover(
                self,
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                entry.data.get(CONF_COUNTRY_CODE, "NL"),
            )
            if error is None and entry.data[CONF_DEVICE_CID] not in fryers:
                error = "device_missing"
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                )
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"username": entry.data[CONF_USERNAME]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return TwinFryOptionsFlow()


class TwinFryOptionsFlow(OptionsFlow):
    """Start method, SwitchBot and timing options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and validate the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate(user_input)
            if not errors:
                cleaned = {k: v for k, v in user_input.items() if v not in (None, "")}
                return self.async_create_entry(data=cleaned)

        options = {**self.config_entry.options, **(user_input or {})}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_START_METHOD,
                    default=options.get(CONF_START_METHOD, StartMethod.NATIVE.value),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[m.value for m in StartMethod],
                        translation_key="start_method",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_SWITCHBOT_ENTITY,
                    description={"suggested_value": options.get(CONF_SWITCHBOT_ENTITY)},
                ): EntitySelector(EntitySelectorConfig(domain=list(SWITCHBOT_DOMAINS))),
                vol.Required(
                    CONF_PRESS_DELAY,
                    default=options.get(CONF_PRESS_DELAY, DEFAULT_PRESS_DELAY),
                ): _number(0, 30),
                vol.Required(
                    CONF_READY_TIMEOUT,
                    default=options.get(CONF_READY_TIMEOUT, DEFAULT_READY_TIMEOUT),
                ): _number(5, 120),
                vol.Required(
                    CONF_CONFIRM_TIMEOUT,
                    default=options.get(CONF_CONFIRM_TIMEOUT, DEFAULT_CONFIRM_TIMEOUT),
                ): _number(10, 180),
                vol.Required(
                    CONF_SCAN_INTERVAL_ACTIVE,
                    default=options.get(CONF_SCAN_INTERVAL_ACTIVE, DEFAULT_SCAN_INTERVAL_ACTIVE),
                ): _number(5, 60),
                vol.Required(
                    CONF_SCAN_INTERVAL_IDLE,
                    default=options.get(CONF_SCAN_INTERVAL_IDLE, DEFAULT_SCAN_INTERVAL_IDLE),
                ): _number(15, 600),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    def _validate(self, user_input: dict[str, Any]) -> dict[str, str]:
        method = user_input.get(CONF_START_METHOD)
        entity_id = user_input.get(CONF_SWITCHBOT_ENTITY)
        if method == StartMethod.SWITCHBOT and not entity_id:
            return {CONF_SWITCHBOT_ENTITY: "switchbot_required"}
        if entity_id:
            if entity_id.split(".", 1)[0] not in SWITCHBOT_DOMAINS:
                return {CONF_SWITCHBOT_ENTITY: "switchbot_wrong_domain"}
            state = self.hass.states.get(entity_id)
            if state is None:
                return {CONF_SWITCHBOT_ENTITY: "switchbot_not_found"}
            if entity_id.startswith("switch.") and state.attributes.get("switch_mode") is True:
                return {CONF_SWITCHBOT_ENTITY: "switchbot_switch_mode"}
        return {}
