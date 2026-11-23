"""Config flow, options, and reauth. The password stays in the entry."""

from __future__ import annotations

import pytest
from custom_components.cl6.client import Cl6AuthError, Cl6ConnectionError
from custom_components.cl6.const import CONF_EMAIL, CONF_PASSWORD, DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.common import EMAIL, PASSWORD

pytestmark = pytest.mark.usefixtures("enable_cl6")


async def test_single_car_creates_an_entry(hass, mock_connect):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD},
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Her Car"
    assert result["data"][CONF_PASSWORD] == PASSWORD
    assert CONF_PASSWORD not in result["options"]
    assert result["data"]["asset_id"] == 7
    assert mock_connect.passwords
    assert set(mock_connect.passwords) == {PASSWORD}


async def test_several_cars_asks_which_one(hass, mock_connect):
    mock_connect.assets = [
        {"id": 7, "name": "Her Car"},
        {"id": 8, "name": "Truck"},
    ]
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "vehicle"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"asset_id": "8"},
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Truck"
    assert result["data"]["asset_id"] == 8
    assert result["data"]["account_id"] == 42


async def test_bad_password_and_unreachable(hass, mock_connect):
    mock_connect.connect_error = Cl6AuthError("rejected")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD},
    )
    assert result["errors"]["base"] == "invalid_auth"

    mock_connect.connect_error = Cl6ConnectionError("down")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD},
    )
    assert result["errors"]["base"] == "cannot_connect"


async def test_same_car_is_not_added_twice(hass, mock_connect):
    MockConfigEntry(domain=DOMAIN, unique_id="42:7", data={}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD},
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_reauth_updates_the_password(hass, cl6_entry, mock_connect):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reauth",
            "entry_id": cl6_entry.entry_id,
            "unique_id": cl6_entry.unique_id,
        },
        data=dict(cl6_entry.data),
    )
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PASSWORD: "replacement-password"},
    )
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert cl6_entry.data[CONF_PASSWORD] == "replacement-password"
    assert EMAIL not in result["reason"]


async def test_options_save_the_polling_interval(hass, cl6_entry):
    from datetime import timedelta

    from custom_components.cl6.const import DOMAIN as CL6

    result = await hass.config_entries.options.async_init(cl6_entry.entry_id)
    assert result["type"] == "form"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "scan_interval": 15,
            "max_run_minutes": 12,
            "extend_once": True,
            "confirm_seconds": 45,
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    coordinator = hass.data[CL6]["entries"][cl6_entry.entry_id]
    assert coordinator.update_interval == timedelta(minutes=15)
    assert coordinator.max_run_minutes == 12
    assert coordinator.extend_once is True
    assert coordinator.confirm_seconds == 45
    assert "password" not in cl6_entry.options
