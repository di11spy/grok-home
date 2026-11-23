"""Config and options flow for CL6.

The password is stored only in the config entry. It is not written to options,
logs, or source files.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow, callback
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.selector import (
    BooleanSelector,
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

from . import client as cl6_client
from .client import Cl6ApiError, Cl6AuthError, Cl6ConnectionError, Cl6NoVehicles, Cl6Timeout
from .const import (
    CONF_ACCOUNT_ID,
    CONF_ASSET_ID,
    CONF_CONFIRM_SECONDS,
    CONF_EXTEND_ONCE,
    CONF_MAX_RUN_MINUTES,
    CONF_SCAN_INTERVAL,
    CONF_VEHICLE_NAME,
    DEFAULT_CONFIRM_SECONDS,
    DEFAULT_MAX_RUN_MINUTES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_CONFIRM_SECONDS,
    MAX_MAX_RUN_MINUTES,
    MAX_SCAN_INTERVAL,
    MIN_CONFIRM_SECONDS,
    MIN_MAX_RUN_MINUTES,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _error_key(err: Exception) -> str:
    if isinstance(err, Cl6AuthError):
        return "invalid_auth"
    if isinstance(err, (Cl6ConnectionError, Cl6Timeout)):
        return "cannot_connect"
    if isinstance(err, Cl6NoVehicles):
        return "no_vehicles"
    return "unknown"


def _number(low: int, high: int, unit: str):
    return NumberSelector(
        NumberSelectorConfig(
            min=low,
            max=high,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


class Cl6ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the MyCarControls login, then the car."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None
        self._account_id: Any = None
        self._assets: list[dict[str, Any]] = []
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            email = str(user_input[CONF_EMAIL]).strip()
            password = user_input[CONF_PASSWORD]
            try:
                account_id, assets = await self.hass.async_add_executor_job(
                    cl6_client.validate_login, email, password
                )
            except (
                Cl6AuthError,
                Cl6ConnectionError,
                Cl6Timeout,
                Cl6ApiError,
                Cl6NoVehicles,
            ) as err:
                errors["base"] = _error_key(err)
                _LOGGER.debug("CL6 setup did not sign in: %s", type(err).__name__)
            else:
                self._email = email
                self._password = password
                self._account_id = account_id
                self._assets = assets
                if len(assets) == 1:
                    return await self._async_create(assets[0])
                return await self.async_step_vehicle()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): _PASSWORD,
                }
            ),
            errors=errors,
        )

    async def async_step_vehicle(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        options = [
            {"label": str(asset["name"]), "value": str(asset["id"])} for asset in self._assets
        ]
        if user_input is not None:
            chosen = str(user_input[CONF_ASSET_ID])
            match = next((asset for asset in self._assets if str(asset["id"]) == chosen), None)
            if match is None:
                errors["base"] = "no_vehicles"
            else:
                return await self._async_create(match)

        return self.async_show_form(
            step_id="vehicle",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ASSET_ID): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
            errors=errors,
        )

    async def _async_create(self, asset: dict[str, Any]):
        unique_id = f"{self._account_id}:{asset['id']}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        name = str(asset["name"])
        return self.async_create_entry(
            title=name,
            data={
                CONF_EMAIL: self._email,
                CONF_PASSWORD: self._password,
                CONF_ACCOUNT_ID: self._account_id,
                CONF_ASSET_ID: asset["id"],
                CONF_VEHICLE_NAME: name,
            },
            options={
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                CONF_MAX_RUN_MINUTES: DEFAULT_MAX_RUN_MINUTES,
                CONF_EXTEND_ONCE: False,
                CONF_CONFIRM_SECONDS: DEFAULT_CONFIRM_SECONDS,
            },
        )

    async def async_step_reauth(self, _entry_data: dict[str, Any]):
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        assert entry is not None
        email = entry.data[CONF_EMAIL]
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            try:
                await self.hass.async_add_executor_job(cl6_client.validate_login, email, password)
            except (
                Cl6AuthError,
                Cl6ConnectionError,
                Cl6Timeout,
                Cl6ApiError,
                Cl6NoVehicles,
            ) as err:
                errors["base"] = _error_key(err)
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD}),
            errors=errors,
            description_placeholders={"email": str(email)},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> Cl6OptionsFlow:
        return Cl6OptionsFlow()


class Cl6OptionsFlow(OptionsFlow):
    """Polling, run time, cold-day extend, and the confirmation window."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        current = self.config_entry.options
        if user_input is not None:
            scan = int(user_input[CONF_SCAN_INTERVAL])
            run = int(user_input[CONF_MAX_RUN_MINUTES])
            window = int(user_input[CONF_CONFIRM_SECONDS])
            if not MIN_SCAN_INTERVAL <= scan <= MAX_SCAN_INTERVAL:
                errors[CONF_SCAN_INTERVAL] = "invalid_scan"
            elif not MIN_MAX_RUN_MINUTES <= run <= MAX_MAX_RUN_MINUTES:
                errors[CONF_MAX_RUN_MINUTES] = "invalid_run"
            elif not MIN_CONFIRM_SECONDS <= window <= MAX_CONFIRM_SECONDS:
                errors[CONF_CONFIRM_SECONDS] = "invalid_window"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SCAN_INTERVAL: scan,
                        CONF_MAX_RUN_MINUTES: run,
                        CONF_EXTEND_ONCE: bool(user_input[CONF_EXTEND_ONCE]),
                        CONF_CONFIRM_SECONDS: window,
                    },
                )

        def _default(key: str, fallback: int) -> int:
            try:
                return int(current.get(key, fallback))
            except (TypeError, ValueError):
                return fallback

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=_default(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): _number(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL, "min"),
                    vol.Required(
                        CONF_MAX_RUN_MINUTES,
                        default=_default(CONF_MAX_RUN_MINUTES, DEFAULT_MAX_RUN_MINUTES),
                    ): _number(MIN_MAX_RUN_MINUTES, MAX_MAX_RUN_MINUTES, "min"),
                    vol.Required(
                        CONF_EXTEND_ONCE,
                        default=bool(current.get(CONF_EXTEND_ONCE, False)),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_CONFIRM_SECONDS,
                        default=_default(CONF_CONFIRM_SECONDS, DEFAULT_CONFIRM_SECONDS),
                    ): _number(MIN_CONFIRM_SECONDS, MAX_CONFIRM_SECONDS, "s"),
                }
            ),
            errors=errors,
        )
