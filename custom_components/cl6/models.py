"""Snapshots shared by the coordinator and entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Cl6Data:
    """Latest car status plus the last command this integration sent."""

    latitude: float | None
    longitude: float | None
    speed: float | None
    heading: float | None
    voltage: float | None
    rssi: float | None
    gps_time: datetime | None
    gps_time_raw: str | None
    gps_status: str | None
    engine_on: bool | None
    ignition_on: bool | None
    doors_open: bool | None
    online: bool | None
    locked: bool | None
    engine_raw: str | None
    ignition_raw: str | None
    door_raw: str | None
    online_raw: str | None
    engine_shutdown_raw: str | None
    last_command: str | None
    last_result: str | None
    last_source: str | None
    last_command_id: str | None
    last_command_at: datetime | None
    pending_command_id: str | None
    arm_action: str | None
    arm_expires: datetime | None
    run_active: bool
