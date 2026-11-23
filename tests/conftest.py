"""Shared fixtures for the CL6 tests.

Nothing in this suite contacts the CL6 service.
"""

from __future__ import annotations

from typing import Any

import pytest
from custom_components.cl6.client import Cl6AuthError
from custom_components.cl6.const import DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.common import EMAIL, PASSWORD


def sample_status(**overrides: Any) -> dict[str, Any]:
    """A full DeviceStatus payload. Tests change one field at a time."""
    payload: dict[str, Any] = {
        "GpsStatus": "Valid",
        "GpsDateTime": "2026-01-15T12:30:00+00:00",
        "Latitude": 47.6062,
        "Longitude": -122.3321,
        "Speed": 0,
        "Heading": 90,
        "ExternalVoltage": 12.4,
        "Rssi": 84,
        "DoorStatus": "Closed",
        "EngineStatus": "Off",
        "IgnitionStatus": "Off",
        "Alarm": "Off",
        "EngineShutdownDateTime": None,
        "BypassUpdatedDateTime": None,
        "BypassTemperature": None,
        "Online": True,
    }
    payload.update(overrides)
    return payload


class FakeCL6:
    """Stand-in for Cl6Client. Records commands and never opens a socket."""

    def __init__(self) -> None:
        self.account_id = 42
        self.asset_id = 7
        self.asset_name = "Her Car"
        self.assets = [{"id": 7, "name": "Her Car"}]
        self.status = sample_status()
        self.submits: list[str] = []
        self.status_checks: list[Any] = []
        self.relogins = 0
        self.command_seq = 1000
        self.next_command_status = "Success"
        self.fail_submit: str | None = None
        self.auth_failures = 0
        self.connect_error: Exception | None = None
        self.relogin_error: Exception | None = None
        self.emails: list[str] = []
        self.passwords: list[str] = []

    def list_assets(self) -> list[dict[str, Any]]:
        return list(self.assets)

    def get_status(self) -> dict[str, Any]:
        if self.auth_failures:
            self.auth_failures -= 1
            raise Cl6AuthError("rejected")
        return dict(self.status)

    def submit_command(self, command_type: str) -> int:
        self.submits.append(command_type)
        if self.fail_submit == "timeout":
            self.fail_submit = None
            from custom_components.cl6.client import Cl6Timeout

            raise Cl6Timeout("timed out")
        if self.fail_submit == "auth":
            self.fail_submit = None
            raise Cl6AuthError("rejected")
        if self.fail_submit == "connection":
            self.fail_submit = None
            from custom_components.cl6.client import Cl6ConnectionError

            raise Cl6ConnectionError("down")
        self.command_seq += 1
        return self.command_seq

    def command_status(self, command_id: Any) -> str:
        self.status_checks.append(command_id)
        return self.next_command_status

    def relogin(self) -> None:
        self.relogins += 1
        if self.relogin_error is not None:
            raise self.relogin_error


@pytest.fixture
def fake_cl6() -> FakeCL6:
    return FakeCL6()


@pytest.fixture
def mock_connect(fake_cl6: FakeCL6, monkeypatch: pytest.MonkeyPatch):
    """Replace login so config flow and setup share one fake car."""

    def _connect(email, password, asset_id=None, load_status=True):
        if fake_cl6.connect_error is not None:
            raise fake_cl6.connect_error
        fake_cl6.emails.append(email)
        fake_cl6.passwords.append(password)
        if asset_id is not None:
            fake_cl6.asset_id = asset_id
        return fake_cl6

    monkeypatch.setattr("custom_components.cl6.client.connect", _connect)
    return fake_cl6


@pytest.fixture(autouse=True)
def fast_command_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real client waits 10 seconds between polls. Tests do not."""
    monkeypatch.setattr("custom_components.cl6.const.POLL_DELAY_SECONDS", 0)


@pytest.fixture
async def cl6_entry(hass, mock_connect, enable_cl6):
    """A configured car with a short confirmation window and a 1 minute run."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "email": EMAIL,
            "password": PASSWORD,
            "account_id": 42,
            "asset_id": 7,
            "vehicle_name": "Her Car",
        },
        options={
            "scan_interval": 5,
            "max_run_minutes": 1,
            "extend_once": False,
            "confirm_seconds": 10,
        },
        unique_id="42:7",
        title="Her Car",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def enable_cl6(enable_custom_integrations):
    """Load this repo as a custom integration."""
    return enable_custom_integrations
