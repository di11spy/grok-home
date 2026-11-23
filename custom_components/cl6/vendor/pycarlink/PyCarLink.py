"""Unofficial Carlink / MyCarControls / CL6 client.

Vendored from https://github.com/angel12/PyCarLink at commit
a11d551491fc8e6025c7d68314cc7666d040cbac. See VENDOR.md.

The service is the M2M Suite API documented at https://www.m2msuite.com/Api/Rest.
"""

from __future__ import annotations

import base64
import logging
import sys
import time

import requests

BASE_URL = "https://api.m2msuite.com/v1.1/109.3/"

# DoorUnLock is the spelling the service expects.
COMMAND_ENGINE_START = "EngineStart"
COMMAND_ENGINE_STOP = "EngineStop"
COMMAND_DOOR_LOCK = "DoorLock"
COMMAND_DOOR_UNLOCK = "DoorUnLock"

_NAME_KEYS = ("Name", "AssetName", "Description", "Label", "DeviceName")
_STATUS_FIELDS = (
    "GpsStatus",
    "GpsDateTime",
    "Latitude",
    "Longitude",
    "Speed",
    "Heading",
    "ExternalVoltage",
    "Rssi",
    "DoorStatus",
    "EngineStatus",
    "IgnitionStatus",
    "Alarm",
    "EngineShutdownDateTime",
    "BypassUpdatedDateTime",
    "BypassTemperature",
    "Online",
)

log = logging.getLogger(__name__)


class MalformedResponseError(ValueError):
    """The service returned JSON or response fields this client cannot use."""


class NoAssetsError(ValueError):
    """The account has no assets for this client to select."""


def _parse_response(response: requests.Response, expected_type: type = dict):
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError:
        raise MalformedResponseError("Response must contain valid JSON.") from None
    if not isinstance(data, expected_type):
        shape = "array" if expected_type is list else "object"
        raise MalformedResponseError("Response must be a JSON " + shape + ".")
    return data


def _required_field(data, field, identifier=False):
    if not isinstance(data, dict):
        raise MalformedResponseError("Response item must be a JSON object.")
    if field not in data:
        raise MalformedResponseError("Response is missing required field " + field + ".")
    value = data[field]
    valid = isinstance(value, str) and bool(value.strip())
    if identifier:
        valid = valid or type(value) is int
    if not valid:
        expected = "a nonempty string or integer" if identifier else "a nonempty string"
        raise MalformedResponseError("Response field " + field + " must be " + expected + ".")
    return value


def _basic_token(value: str) -> str:
    """Encode a Basic-auth token the same way upstream PyCarLink does."""
    encoded = base64.b64encode(value.encode("utf-8"))
    as_text = str(encoded)
    stripped = as_text.rstrip(as_text[-1])
    return stripped[2:]


class PyCarlink:
    """Synchronous client for one CL6 account.

    Constructing with the defaults logs in, selects the first vehicle, and
    fetches status. Pass ``load_status=False`` to stop after login. Pass
    ``asset_id`` to select that vehicle instead of the first one.
    """

    def __init__(
        self,
        email,
        password,
        timeout=(5.0, 30.0),
        asset_id=None,
        load_status=True,
    ):
        if (
            not isinstance(timeout, tuple)
            or len(timeout) != 2
            or any(
                type(value) not in (int, float) or not 0 < value <= sys.float_info.max
                for value in timeout
            )
        ):
            raise ValueError("timeout must be a (connect, read) tuple of positive finite seconds")
        self.timeout = timeout
        self.email = email
        self.password = password
        self.login_auth_header = None
        self.api_key = None
        self.account_id = None
        self.asset_id = None
        self.asset_name = None
        self.assets = []
        self.asset_status = None
        self.command_id = None
        self.api_auth_header = None

        self.login_auth_header = self.create_login_header(email, password)
        self.api_key = self.retrieve_api_key()
        self.account_id = self.retrieve_account_id()
        self.api_auth_header = self.create_api_header()

        if asset_id is not None:
            self.select_asset(asset_id)
        elif load_status:
            self.asset_id = self.get_asset_0()
            self.asset_name = f"Vehicle {self.asset_id}"
            self.assets = [{"id": self.asset_id, "name": self.asset_name}]

        if load_status and self.asset_id is not None:
            self.asset_status = self.get_asset_status()

    def __repr__(self) -> str:
        return f"<PyCarlink account_id={self.account_id!r} asset_id={self.asset_id!r}>"

    def create_login_header(self, email, password):
        """Build the Basic header used only to fetch the API key."""
        login = self.email + ":" + self.password
        auth_string = "Basic" + " " + _basic_token(login)
        self.login_auth_header = {"Authorization": auth_string}
        return self.login_auth_header

    def retrieve_api_key(self):
        url = BASE_URL + "100007/Access"
        response = requests.get(url, headers=self.login_auth_header, timeout=self.timeout)
        json_data = _parse_response(response)
        return _required_field(json_data, "APIKey")

    def retrieve_account_id(self):
        url = BASE_URL + "100007/Access"
        response = requests.get(url, headers=self.login_auth_header, timeout=self.timeout)
        json_data = _parse_response(response)
        return _required_field(json_data, "AccountID", identifier=True)

    def create_api_header(self):
        auth_string = "Basic " + _basic_token("@apikey:" + self.api_key)
        self.api_auth_header = {"Authorization": auth_string}
        return self.api_auth_header

    def relogin(self):
        """Fetch a new API key. Does not send a vehicle command."""
        self.login_auth_header = self.create_login_header(self.email, self.password)
        self.api_key = self.retrieve_api_key()
        self.account_id = self.retrieve_account_id()
        self.api_auth_header = self.create_api_header()

    def get_asset_0(self):
        url = BASE_URL + str(self.account_id) + "/Assets"
        response = requests.get(url, headers=self.api_auth_header, timeout=self.timeout)
        json_data = _parse_response(response, list)
        if not json_data:
            raise NoAssetsError("Account has no assets; add a vehicle before using this client.")
        return _required_field(json_data[0], "ID", identifier=True)

    def list_assets(self):
        """Return ``{"id", "name"}`` for every vehicle on the account."""
        url = BASE_URL + str(self.account_id) + "/Assets"
        response = requests.get(url, headers=self.api_auth_header, timeout=self.timeout)
        json_data = _parse_response(response, list)
        assets = []
        for item in json_data:
            asset_id = _required_field(item, "ID", identifier=True)
            name = None
            for key in _NAME_KEYS:
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    name = value.strip()
                    break
            assets.append({"id": asset_id, "name": name or f"Vehicle {asset_id}"})
        self.assets = assets
        return assets

    def select_asset(self, asset_id):
        """Select one vehicle by id. Raises if it is not on the account."""
        assets = self.list_assets()
        wanted = str(asset_id)
        for asset in assets:
            if str(asset["id"]) == wanted:
                self.asset_id = asset["id"]
                self.asset_name = asset["name"]
                return self.asset_id
        raise NoAssetsError("Requested vehicle was not found on this account.")

    def get_asset_status(self):
        url = BASE_URL + str(self.account_id) + "/DeviceStatus/" + str(self.asset_id)
        response = requests.get(url, headers=self.api_auth_header, timeout=self.timeout)
        json_data = _parse_response(response)
        for field in _STATUS_FIELDS:
            if field not in json_data:
                raise MalformedResponseError(
                    "DeviceStatus response is missing required field " + field + "."
                )
        status = {
            "gpsstatus": json_data["GpsStatus"],
            "gpsdatetime": json_data["GpsDateTime"],
            "latitude": json_data["Latitude"],
            "longitude": json_data["Longitude"],
            "speed": json_data["Speed"],
            "heading": json_data["Heading"],
            "externalvoltage": json_data["ExternalVoltage"],
            "rssi": json_data["Rssi"],
            "doorstatus": json_data["DoorStatus"],
            "enginestatus": json_data["EngineStatus"],
            "ingnitionstatus": json_data["IgnitionStatus"],
            "alarm": json_data["Alarm"],
            "engineshutdowndatetime": json_data["EngineShutdownDateTime"],
            "bypassupdateddatetime": json_data["BypassUpdatedDateTime"],
            "bypasstemperature": json_data["BypassTemperature"],
            "online": json_data["Online"],
            "asset_status": json_data,
        }
        self.__dict__.update(status)
        return json_data

    def submit_command(self, command_type):
        """Post one command and return its id. Does not sleep or poll."""
        url = BASE_URL + str(self.account_id) + "/Commands"
        body = {"DeviceID": self.asset_id, "Type": command_type}
        response = requests.post(url, json=body, headers=self.api_auth_header, timeout=self.timeout)
        data = _parse_response(response)
        self.command_id = _required_field(data, "ID", identifier=True)
        return self.command_id

    def start_engine(self):
        return self._poll_command(self.submit_command(COMMAND_ENGINE_START))

    def stop_engine(self):
        return self._poll_command(self.submit_command(COMMAND_ENGINE_STOP))

    def lock_doors(self):
        return self._poll_command(self.submit_command(COMMAND_DOOR_LOCK))

    def unlock_doors(self):
        return self._poll_command(self.submit_command(COMMAND_DOOR_UNLOCK))

    def _poll_command(self, command_id):
        """Poll an existing command; exhaustion does not establish failure."""
        for _ in range(2):
            time.sleep(10)
            status = self.command_status(command_id)
            if status == "Success":
                return status
            if status not in ("Pending", "Processing"):
                return "Command Failed"
        return "Command Timed Out"

    def command_status(self, command_id):
        url = BASE_URL + str(self.account_id) + "/Commands/" + str(command_id)
        statusresponse = requests.get(url, headers=self.api_auth_header, timeout=self.timeout)
        json_response = _parse_response(statusresponse)
        return _required_field(json_response, "Status")
