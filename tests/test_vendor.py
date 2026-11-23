"""The vendored client posts once and can pick a vehicle by id."""

from __future__ import annotations

import base64
from unittest.mock import Mock, patch

import pytest
import requests
from custom_components.cl6.vendor.pycarlink.PyCarLink import (
    BASE_URL,
    COMMAND_ENGINE_START,
    NoAssetsError,
    PyCarlink,
)


def _response(payload):
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _access():
    return _response({"APIKey": "test-key", "AccountID": 123})


@pytest.fixture
def blocked_network():
    with patch(
        "requests.sessions.Session.request",
        side_effect=AssertionError("Real network is forbidden"),
    ):
        yield


def test_login_header_matches_basic_auth_and_repr_hides_the_password(blocked_network):
    email = "user@example.com"
    password = "s3cret"
    with patch(
        "custom_components.cl6.vendor.pycarlink.PyCarLink.requests.get",
        side_effect=[_access(), _access()],
    ):
        client = PyCarlink(email, password, load_status=False)

    token = client.login_auth_header["Authorization"].split(" ", 1)[1]
    assert base64.b64decode(token).decode() == f"{email}:{password}"
    assert password not in repr(client)
    assert email not in repr(client)
    assert "test-key" not in repr(client)


def test_select_asset_uses_the_requested_id(blocked_network):
    assets = [
        {"ID": 1, "Name": "First"},
        {"ID": 2, "Name": "Second"},
    ]
    with patch(
        "custom_components.cl6.vendor.pycarlink.PyCarLink.requests.get",
        side_effect=[_access(), _access(), _response(assets)],
    ):
        client = PyCarlink("user@example.com", "s3cret", asset_id=2, load_status=False)

    assert client.asset_id == 2
    assert client.asset_name == "Second"


def test_missing_vehicle_raises(blocked_network):
    with (
        patch(
            "custom_components.cl6.vendor.pycarlink.PyCarLink.requests.get",
            side_effect=[_access(), _access(), _response([{"ID": 1, "Name": "Only"}])],
        ),
        pytest.raises(NoAssetsError),
    ):
        PyCarlink("user@example.com", "s3cret", asset_id=99, load_status=False)


def test_submit_command_posts_once_and_does_not_sleep(blocked_network):
    with (
        patch(
            "custom_components.cl6.vendor.pycarlink.PyCarLink.requests.get",
            side_effect=[_access(), _access()],
        ),
        patch("custom_components.cl6.vendor.pycarlink.PyCarLink.requests.post") as post,
        patch("custom_components.cl6.vendor.pycarlink.PyCarLink.time.sleep") as sleep,
    ):
        client = PyCarlink("user@example.com", "s3cret", load_status=False)
        client.asset_id = 456
        post.return_value = _response({"ID": 789})
        command_id = client.submit_command(COMMAND_ENGINE_START)

    assert command_id == 789
    post.assert_called_once()
    assert post.call_args.args == (BASE_URL + "123/Commands",)
    assert post.call_args.kwargs["json"] == {"DeviceID": 456, "Type": "EngineStart"}
    sleep.assert_not_called()


def test_blocking_start_still_polls_and_timeout_is_unknown(blocked_network):
    with (
        patch(
            "custom_components.cl6.vendor.pycarlink.PyCarLink.requests.get",
            side_effect=[
                _access(),
                _access(),
                _response({"Status": "Pending"}),
                _response({"Status": "Pending"}),
            ],
        ),
        patch("custom_components.cl6.vendor.pycarlink.PyCarLink.requests.post") as post,
        patch("custom_components.cl6.vendor.pycarlink.PyCarLink.time.sleep") as sleep,
    ):
        client = PyCarlink("user@example.com", "s3cret", load_status=False)
        client.asset_id = 456
        post.return_value = _response({"ID": 789})
        result = client.start_engine()

    assert result == "Command Timed Out"
    post.assert_called_once()
    assert sleep.call_count == 2


def test_http_401_is_not_rewritten_by_the_vendor(blocked_network):
    denied = Mock()
    denied.raise_for_status.side_effect = requests.HTTPError(response=Mock(status_code=401))
    with (
        patch("custom_components.cl6.vendor.pycarlink.PyCarLink.requests.get", return_value=denied),
        pytest.raises(requests.HTTPError),
    ):
        PyCarlink("user@example.com", "s3cret", load_status=False)
