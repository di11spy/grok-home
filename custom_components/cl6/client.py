"""Login and command wrapper around the vendored PyCarLink client.

Exceptions raised here never include the email, password, headers, or the
service's raw body. A timeout or a lost connection during a command does not
mean the car missed it, so callers must not send that command again.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from .vendor.pycarlink import MalformedResponseError, NoAssetsError, PyCarlink

_LOGGER = logging.getLogger(__name__)


class Cl6Error(Exception):
    """Base error that is safe to show and to log."""


class Cl6AuthError(Cl6Error):
    """The email or password was rejected."""


class Cl6ConnectionError(Cl6Error):
    """The CL6 service could not be reached."""


class Cl6Timeout(Cl6Error):
    """The service did not answer in time."""


class Cl6ApiError(Cl6Error):
    """The service answered with something this integration cannot use."""


class Cl6NoVehicles(Cl6ApiError):
    """The account has no vehicles, or the chosen one is gone."""


def _translate(exc: Exception) -> Exception:
    """Return a safe error. The original exception is not chained."""
    if isinstance(exc, Cl6Error):
        return exc
    _LOGGER.debug("CL6 request failed with %s", type(exc).__name__)
    if isinstance(exc, NoAssetsError):
        return Cl6NoVehicles("No vehicles on this account")
    if isinstance(exc, MalformedResponseError):
        return Cl6ApiError("Unexpected response from CL6")
    if isinstance(exc, requests.Timeout):
        return Cl6Timeout("CL6 timed out")
    if isinstance(exc, requests.ConnectionError):
        return Cl6ConnectionError("CL6 unreachable")
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        if status in (401, 403):
            return Cl6AuthError("CL6 rejected the login")
        return Cl6ApiError("CL6 returned an error")
    if isinstance(exc, requests.RequestException):
        return Cl6ConnectionError("CL6 unreachable")
    return Cl6ApiError("Unexpected CL6 error")


def _run(func):
    try:
        return func()
    except Exception as err:
        raise _translate(err) from None


class Cl6Client:
    """Small synchronous API used by the coordinator from an executor."""

    def __init__(self, raw: PyCarlink) -> None:
        self._raw = raw

    def __repr__(self) -> str:
        return repr(self._raw)

    @property
    def account_id(self) -> Any:
        return self._raw.account_id

    @property
    def asset_id(self) -> Any:
        return self._raw.asset_id

    @property
    def asset_name(self) -> str:
        name = self._raw.asset_name
        if isinstance(name, str) and name.strip():
            return name.strip()
        return f"Vehicle {self._raw.asset_id}"

    def list_assets(self) -> list[dict[str, Any]]:
        return _run(self._raw.list_assets)

    def get_status(self) -> dict[str, Any]:
        return _run(self._raw.get_asset_status)

    def submit_command(self, command_type: str) -> Any:
        return _run(lambda: self._raw.submit_command(command_type))

    def command_status(self, command_id: Any) -> str:
        return _run(lambda: self._raw.command_status(command_id))

    def relogin(self) -> None:
        _run(self._raw.relogin)


def connect(
    email: str,
    password: str,
    asset_id: Any = None,
    load_status: bool = True,
) -> Cl6Client:
    """Log in. Vehicle status is loaded unless ``load_status`` is false."""

    def _build() -> Cl6Client:
        raw = PyCarlink(
            email,
            password,
            asset_id=asset_id,
            load_status=load_status,
        )
        return Cl6Client(raw)

    return _run(_build)


def validate_login(email: str, password: str) -> tuple[Any, list[dict[str, Any]]]:
    """Log in once and return the account id plus the vehicle list."""
    client = connect(email, password, load_status=False)
    assets = client.list_assets()
    if not assets:
        raise Cl6NoVehicles("No vehicles on this account")
    return client.account_id, assets
