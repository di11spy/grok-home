"""Polling, confirmation, and the remote-start timer.

HTTP calls run in an executor. The 10 second gaps between command polls are
``asyncio.sleep``, so the Home Assistant event loop keeps running.

A command is posted once. If the answer is missing, the result is unknown and
the same command is not posted again. A later poll may check the command id.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.logbook import async_log_entry
from homeassistant.components.persistent_notification import async_create, async_dismiss
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import const
from .client import (
    Cl6ApiError,
    Cl6AuthError,
    Cl6Client,
    Cl6ConnectionError,
    Cl6Timeout,
)
from .const import (
    ACTION_LOCK,
    ACTION_START,
    ACTION_STOP,
    ACTION_UNLOCK,
    API_COMMANDS,
    CONF_CONFIRM_SECONDS,
    CONF_EXTEND_ONCE,
    CONF_MAX_RUN_MINUTES,
    CONF_SCAN_INTERVAL,
    DEFAULT_CONFIRM_SECONDS,
    DEFAULT_MAX_RUN_MINUTES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_COMMAND,
    MAX_CONFIRM_SECONDS,
    MAX_MAX_RUN_MINUTES,
    MAX_SCAN_INTERVAL,
    MIN_CONFIRM_SECONDS,
    MIN_MAX_RUN_MINUTES,
    MIN_SCAN_INTERVAL,
    RESULT_FAILED,
    RESULT_SUCCESS,
    RESULT_UNKNOWN,
    SOURCE_EXTEND,
    SOURCE_MAX_RUN,
    SOURCE_SPEED,
    SUCCESS_STATUS,
)
from .models import Cl6Data
from .parser import parse_speed, vehicle_from_status

_LOGGER = logging.getLogger(__name__)

_ACTION_WORDS = {
    ACTION_START: "remote start",
    ACTION_STOP: "engine stop",
    ACTION_LOCK: "door lock",
    ACTION_UNLOCK: "door unlock",
}
_SOURCE_WORDS = {
    "button": "the dashboard",
    "lock": "the door lock",
    "service": "a service call",
    "assist": "voice",
    SOURCE_MAX_RUN: "the run timer",
    SOURCE_EXTEND: "the cold-day second start",
    SOURCE_SPEED: "the car reporting speed above 0",
}


@dataclass
class _Arm:
    action: str
    source: str
    expires: datetime
    token: int


@dataclass
class _Session:
    extend_once: bool
    extended: bool = False
    stop_sent: bool = False
    ends_at: datetime | None = None


def _clamp(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(high, max(low, number))


class Cl6Coordinator(DataUpdateCoordinator[Cl6Data]):
    """One car: status polling, arm/confirm, and the remote-start watchdog."""

    def __init__(self, hass: HomeAssistant, entry, client: Cl6Client) -> None:
        self.entry = entry
        self.client = client
        self.device_key = f"{entry.data.get('account_id')}:{entry.data.get('asset_id')}"
        self.vehicle_name = entry.data.get("vehicle_name") or entry.title or "CL6"
        scan = self.scan_interval_minutes
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan),
            config_entry=entry,
        )
        self._raw: dict[str, Any] | None = None
        self._assumed_lock: bool | None = None
        self._last_command: str | None = None
        self._last_result: str | None = None
        self._last_source: str | None = None
        self._last_command_id: str | None = None
        self._last_at: datetime | None = None
        self._pending_command_id: str | None = None
        self._arm: _Arm | None = None
        self._arm_token = 0
        self._arm_unsub = None
        self._session: _Session | None = None
        self._timer_token = 0
        self._timer_unsub = None
        self._lock = asyncio.Lock()
        self._reauth_started = False
        self._speed_task_pending = False
        self.async_add_listener(self._on_data)

    @property
    def scan_interval_minutes(self) -> int:
        return _clamp(
            self.entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            DEFAULT_SCAN_INTERVAL,
            MIN_SCAN_INTERVAL,
            MAX_SCAN_INTERVAL,
        )

    @property
    def max_run_minutes(self) -> int:
        return _clamp(
            self.entry.options.get(CONF_MAX_RUN_MINUTES, DEFAULT_MAX_RUN_MINUTES),
            DEFAULT_MAX_RUN_MINUTES,
            MIN_MAX_RUN_MINUTES,
            MAX_MAX_RUN_MINUTES,
        )

    @property
    def confirm_seconds(self) -> int:
        return _clamp(
            self.entry.options.get(CONF_CONFIRM_SECONDS, DEFAULT_CONFIRM_SECONDS),
            DEFAULT_CONFIRM_SECONDS,
            MIN_CONFIRM_SECONDS,
            MAX_CONFIRM_SECONDS,
        )

    @property
    def extend_once(self) -> bool:
        return bool(self.entry.options.get(CONF_EXTEND_ONCE, False))

    @property
    def pending_action(self) -> str | None:
        arm = self._arm
        if arm is None or dt_util.utcnow() > arm.expires:
            return None
        return arm.action

    def apply_options(self) -> None:
        """Use a new polling interval without dropping an active remote start."""
        self.update_interval = timedelta(minutes=self.scan_interval_minutes)

    async def async_shutdown(self) -> None:
        self._cancel_timer()
        self._cancel_arm()
        await super().async_shutdown()

    async def _async_update_data(self) -> Cl6Data:
        async with self._lock:
            self._raw = await self._fetch_status()
            await self._resolve_pending()
            return self._compose()

    async def async_arm(self, action: str, source: str) -> None:
        """Arm a start or unlock. Nothing is sent to the car."""
        if action not in (ACTION_START, ACTION_UNLOCK):
            raise ServiceValidationError("Only start and unlock need confirmation.")
        async with self._lock:
            self._cancel_arm()
            self._arm_token += 1
            token = self._arm_token
            expires = dt_util.utcnow() + timedelta(seconds=self.confirm_seconds)
            self._arm = _Arm(action=action, source=source, expires=expires, token=token)

            async def _expire(now: datetime) -> None:
                await self._expire_arm(token)

            self._arm_unsub = async_track_point_in_utc_time(self.hass, _expire, expires)
            data = self._compose()
            seconds = self.confirm_seconds
        self.async_set_updated_data(data)
        self._notify_arm(action, seconds)
        self._announce(action, source, None, None, "armed")

    async def async_confirm(self, source: str) -> str:
        """Send the armed action once. The arm is used up either way."""
        async with self._lock:
            arm = self._arm
            if arm is None or dt_util.utcnow() > arm.expires:
                action = arm.action if arm else None
                self._cancel_arm()
                data = self._compose()
                expired = True
            else:
                action = arm.action
                self._cancel_arm()
                result, command_id = await self._send(action)
                self._record(action, source, result, command_id)
                if action == ACTION_START and result in (RESULT_SUCCESS, RESULT_UNKNOWN):
                    self._begin_session()
                await self._refresh_status()
                data = self._compose()
                expired = False
        self.async_set_updated_data(data)
        self._dismiss_notice()
        if expired:
            if action:
                self._announce(action, source, None, None, "expired")
            raise ServiceValidationError(
                "Nothing is waiting to be confirmed. Arm a start or unlock first. "
                "Nothing was sent to the car."
            )
        self._announce(action, source, result, command_id, "sent")
        return result

    async def async_execute(self, action: str, source: str) -> str:
        """Send stop or lock immediately. Start and unlock are refused."""
        if action not in (ACTION_STOP, ACTION_LOCK):
            raise ServiceValidationError("Start and unlock have to be armed, then confirmed.")
        async with self._lock:
            result, command_id = await self._send(action)
            self._record(action, source, result, command_id)
            if action == ACTION_STOP:
                self._clear_session()
            if action == ACTION_LOCK and result == RESULT_SUCCESS:
                self._assumed_lock = True
            await self._refresh_status()
            data = self._compose()
        self.async_set_updated_data(data)
        self._announce(action, source, result, command_id, "sent")
        return result

    async def _expire_arm(self, token: int) -> None:
        async with self._lock:
            arm = self._arm
            if arm is None or arm.token != token:
                return
            action = arm.action
            source = arm.source
            self._cancel_arm()
            data = self._compose()
        self.async_set_updated_data(data)
        self._dismiss_notice()
        self._announce(action, source, None, None, "expired")

    async def _on_timer(self, now: datetime, token: int) -> None:
        async with self._lock:
            session = self._session
            if token != self._timer_token or session is None or session.stop_sent:
                return
            announcements: list[tuple] = []
            speed = self._current_speed()
            if speed is not None and speed > 0:
                session.stop_sent = True
                result, command_id = await self._send(ACTION_STOP)
                self._record(ACTION_STOP, SOURCE_SPEED, result, command_id)
                await self._refresh_status()
                self._clear_session()
                announcements.append((ACTION_STOP, SOURCE_SPEED, result, command_id))
            elif session.extend_once and not session.extended:
                session.extended = True
                result, command_id = await self._send(ACTION_START)
                self._record(ACTION_START, SOURCE_EXTEND, result, command_id)
                await self._refresh_status()
                announcements.append((ACTION_START, SOURCE_EXTEND, result, command_id))
                if result == RESULT_FAILED:
                    stop_result, stop_id = await self._send(ACTION_STOP)
                    self._record(ACTION_STOP, SOURCE_MAX_RUN, stop_result, stop_id)
                    await self._refresh_status()
                    self._clear_session()
                    announcements.append((ACTION_STOP, SOURCE_MAX_RUN, stop_result, stop_id))
                else:
                    self._schedule_timer()
            else:
                session.stop_sent = True
                result, command_id = await self._send(ACTION_STOP)
                self._record(ACTION_STOP, SOURCE_MAX_RUN, result, command_id)
                await self._refresh_status()
                self._clear_session()
                announcements.append((ACTION_STOP, SOURCE_MAX_RUN, result, command_id))
            data = self._compose()
        self.async_set_updated_data(data)
        for action, source, result, command_id in announcements:
            self._announce(action, source, result, command_id, "sent")

    @callback
    def _on_data(self) -> None:
        """Stop a remote start that this integration began if the car is moving."""
        if self._speed_task_pending:
            return
        session = self._session
        if session is None or session.stop_sent or self.data is None:
            return
        speed = self.data.speed
        if speed is None or speed <= 0:
            return
        self._speed_task_pending = True
        self.hass.async_create_task(self._speed_stop())

    async def _speed_stop(self) -> None:
        try:
            async with self._lock:
                session = self._session
                speed = self._current_speed()
                if session is None or session.stop_sent or speed is None or speed <= 0:
                    return
                session.stop_sent = True
                result, command_id = await self._send(ACTION_STOP)
                self._record(ACTION_STOP, SOURCE_SPEED, result, command_id)
                await self._refresh_status()
                self._clear_session()
                data = self._compose()
            self.async_set_updated_data(data)
            self._announce(ACTION_STOP, SOURCE_SPEED, result, command_id, "sent")
        finally:
            self._speed_task_pending = False

    async def _fetch_status(self) -> dict[str, Any]:
        try:
            return await self._status_once()
        except Cl6AuthError:
            _LOGGER.warning("CL6 rejected the saved login. Signing in again.")
            try:
                await self.hass.async_add_executor_job(self.client.relogin)
                payload = await self._status_once()
            except Cl6AuthError:
                self._start_reauth()
                raise UpdateFailed("CL6 login expired") from None
            except Cl6Timeout:
                raise UpdateFailed("CL6 timed out") from None
            except Cl6ConnectionError:
                raise UpdateFailed("CL6 unreachable") from None
            except Cl6ApiError:
                raise UpdateFailed("CL6 returned an unexpected response") from None
            self._reauth_started = False
            return payload
        except Cl6Timeout:
            raise UpdateFailed("CL6 timed out") from None
        except Cl6ConnectionError:
            raise UpdateFailed("CL6 unreachable") from None
        except Cl6ApiError:
            raise UpdateFailed("CL6 returned an unexpected response") from None

    async def _status_once(self) -> dict[str, Any]:
        payload = await self.hass.async_add_executor_job(self.client.get_status)
        if not isinstance(payload, dict):
            raise Cl6ApiError("Unexpected response from CL6")
        return payload

    async def _refresh_status(self) -> None:
        """One status read after a command. Failure keeps the previous snapshot."""
        try:
            self._raw = await self._fetch_status()
        except UpdateFailed:
            _LOGGER.info("CL6 status refresh after a command did not succeed.")

    async def _send(self, action: str) -> tuple[str, str | None]:
        command_type = API_COMMANDS[action]
        try:
            command_id = await self.hass.async_add_executor_job(
                self.client.submit_command, command_type
            )
        except Cl6AuthError:
            try:
                await self.hass.async_add_executor_job(self.client.relogin)
            except Cl6AuthError:
                self._start_reauth()
            except (Cl6Timeout, Cl6ConnectionError, Cl6ApiError):
                pass
            return RESULT_FAILED, None
        except (Cl6Timeout, Cl6ConnectionError, Cl6ApiError):
            # The post may have reached the car. Do not send it again.
            return RESULT_UNKNOWN, None

        result = await self._poll(command_id)
        text_id = str(command_id)
        if result == RESULT_UNKNOWN:
            self._pending_command_id = text_id
        return result, text_id

    async def _poll(self, command_id: Any) -> str:
        for _attempt in range(const.POLL_ATTEMPTS):
            await asyncio.sleep(const.POLL_DELAY_SECONDS)
            if self.hass.is_stopping:
                return RESULT_UNKNOWN
            try:
                status = await self.hass.async_add_executor_job(
                    self.client.command_status, command_id
                )
            except (Cl6Timeout, Cl6ConnectionError, Cl6ApiError, Cl6AuthError):
                return RESULT_UNKNOWN
            mapped = _map_status(status)
            if mapped != RESULT_UNKNOWN:
                return mapped
        return RESULT_UNKNOWN

    async def _resolve_pending(self) -> None:
        command_id = self._pending_command_id
        if command_id is None:
            return
        try:
            status = await self.hass.async_add_executor_job(self.client.command_status, command_id)
        except (Cl6Timeout, Cl6ConnectionError, Cl6ApiError, Cl6AuthError):
            return
        mapped = _map_status(status)
        if mapped == RESULT_UNKNOWN:
            return
        self._pending_command_id = None
        self._last_result = mapped
        self._announce(
            self._last_command or "command",
            self._last_source or "unknown",
            mapped,
            command_id,
            "resolved",
        )

    def _record(self, action: str, source: str, result: str, command_id: str | None) -> None:
        self._last_command = action
        self._last_source = source
        self._last_result = result
        self._last_command_id = command_id
        self._last_at = dt_util.utcnow()
        if result == RESULT_UNKNOWN and command_id is not None:
            self._pending_command_id = command_id
        elif result != RESULT_UNKNOWN:
            self._pending_command_id = None
        if action == ACTION_LOCK and result == RESULT_SUCCESS:
            self._assumed_lock = True
        if action == ACTION_UNLOCK and result == RESULT_SUCCESS:
            self._assumed_lock = False

    def _begin_session(self) -> None:
        self._clear_session()
        self._session = _Session(extend_once=self.extend_once)
        self._schedule_timer()

    def _schedule_timer(self) -> None:
        if self._timer_unsub is not None:
            self._timer_unsub()
            self._timer_unsub = None
        self._timer_token += 1
        token = self._timer_token
        when = dt_util.utcnow() + timedelta(minutes=self.max_run_minutes)
        if self._session is not None:
            self._session.ends_at = when

        async def _fire(now: datetime) -> None:
            await self._on_timer(now, token)

        self._timer_unsub = async_track_point_in_utc_time(self.hass, _fire, when)

    def _clear_session(self) -> None:
        self._session = None
        self._cancel_timer()

    def _cancel_timer(self) -> None:
        if self._timer_unsub is not None:
            self._timer_unsub()
            self._timer_unsub = None
        self._timer_token += 1

    def _cancel_arm(self) -> None:
        self._arm = None
        if self._arm_unsub is not None:
            self._arm_unsub()
            self._arm_unsub = None

    def _current_speed(self) -> float | None:
        if self._raw is None:
            return None
        return parse_speed(self._raw.get("Speed"))

    def _compose(self) -> Cl6Data:
        arm = self._arm
        if arm is not None and dt_util.utcnow() > arm.expires:
            arm = None
        fields = vehicle_from_status(self._raw, self._assumed_lock)
        return Cl6Data(
            **fields,
            last_command=self._last_command,
            last_result=self._last_result,
            last_source=self._last_source,
            last_command_id=self._last_command_id,
            last_command_at=self._last_at,
            pending_command_id=self._pending_command_id,
            arm_action=None if arm is None else arm.action,
            arm_expires=None if arm is None else arm.expires,
            run_active=self._session is not None and not self._session.stop_sent,
        )

    def _start_reauth(self) -> None:
        if self._reauth_started:
            return
        self._reauth_started = True
        self.entry.async_start_reauth(self.hass)

    def _notify_arm(self, action: str, seconds: int) -> None:
        if action == ACTION_START:
            message = (
                f"Remote start is armed. Press the Confirm button, or say confirm, "
                f"within {seconds} seconds. Nothing has been sent to the car yet."
            )
        else:
            message = (
                f"Unlock is armed. Press the Confirm button, or say confirm, "
                f"within {seconds} seconds. The doors stay as they are until you do."
            )
        async_create(
            self.hass,
            message,
            title="CL6",
            notification_id=self._notice_id,
        )

    def _dismiss_notice(self) -> None:
        async_dismiss(self.hass, self._notice_id)

    @property
    def _notice_id(self) -> str:
        return f"{DOMAIN}_arm_{self.entry.entry_id}"

    def _announce(
        self,
        action: str,
        source: str,
        result: str | None,
        command_id: str | None,
        phase: str,
    ) -> None:
        when = dt_util.utcnow().isoformat()
        _LOGGER.info(
            "CL6 at=%s phase=%s action=%s source=%s result=%s command_id=%s",
            when,
            phase,
            action,
            source,
            result,
            command_id,
        )
        message = _friendly(action, source, result, command_id, phase)
        async_log_entry(self.hass, "CL6", message, DOMAIN, None)
        self.hass.bus.async_fire(
            EVENT_COMMAND,
            {
                "at": when,
                "phase": phase,
                "action": action,
                "source": source,
                "result": result,
                "command_id": command_id,
            },
        )


def _map_status(status: Any) -> str:
    if status == SUCCESS_STATUS:
        return RESULT_SUCCESS
    if status in ("Pending", "Processing"):
        return RESULT_UNKNOWN
    if isinstance(status, str) and status.strip():
        return RESULT_FAILED
    return RESULT_UNKNOWN


def _friendly(
    action: str,
    source: str,
    result: str | None,
    command_id: str | None,
    phase: str,
) -> str:
    name = _ACTION_WORDS.get(action, action)
    via = _SOURCE_WORDS.get(source, source)
    if phase == "armed":
        return f"Armed {name} from {via}. Waiting for confirmation. Nothing was sent to the car."
    if phase == "expired":
        return f"Confirmation expired for {name}. Nothing was sent to the car."
    if phase == "resolved":
        return f"Checked command {command_id} later. Result: {result}."
    extra = ""
    if command_id:
        extra = f" Command {command_id}."
    if result == RESULT_UNKNOWN:
        extra += " It was not sent again."
    return f"Sent {name} from {via}. Result: {result}.{extra}"
