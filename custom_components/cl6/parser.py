"""Turn CL6 status values into numbers and on/off flags.

The live service has not published a value list. These words cover the usual
telematics spellings. Anything else stays unknown, and the raw text is kept
on the entity so it can be checked after the first refresh.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

_FLOAT_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)")
_DOTNET_DATE_RE = re.compile(r"/Date\((-?\d+)\)/")

_NO_FIX = {"invalid", "no fix", "nofix", "no_fix", "none"}

_LOCKED = {"locked", "lock"}
_UNLOCKED = {"unlocked", "unlock"}

_OPEN = {"open", "opened", "ajar"}
_CLOSED = {"closed", "shut"}

_ON = {"1", "true", "on", "yes", "running", "run", "started", "start", "engaged", "active"}
_OFF = {"0", "false", "off", "no", "stopped", "stop", "idle", "parked", "inactive"}

_ONLINE = {"online", "connected", "true", "1", "yes", "on"}
_OFFLINE = {"offline", "disconnected", "false", "0", "no", "off"}


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def raw_value(value: Any) -> str | None:
    """Keep a raw attribute, including booleans and numbers.

    ``_text`` hides booleans so word matching does not treat ``True`` as the
    word "true". The attribute still needs to show what CL6 sent. A JSON
    ``true`` was showing up as an empty raw value.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    return text or None


def parse_float(value: Any) -> float | None:
    """Parse a number. Booleans are not numbers."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = _FLOAT_RE.match(value)
        if match:
            return float(match.group(1))
    return None


def parse_speed(value: Any) -> float | None:
    """Return speed in whatever unit CL6 sent. Unknown stays None."""
    return parse_float(value)


def _word_flag(value: Any, on_words: set[str], off_words: set[str]) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    text = _text(value)
    if text is None:
        return None
    normalized = text.lower()
    if normalized in on_words:
        return True
    if normalized in off_words:
        return False
    return None


def parse_engine(value: Any) -> bool | None:
    """True when the engine is running."""
    return _word_flag(value, _ON, _OFF)


def parse_ignition(value: Any) -> bool | None:
    """True when the ignition is on."""
    return _word_flag(value, _ON | {"accessory", "ignition"}, _OFF | {"lock"})


def parse_online(value: Any) -> bool | None:
    """True when CL6 says the module is online."""
    return _word_flag(value, _ONLINE, _OFFLINE)


def parse_doors_open(value: Any) -> bool | None:
    """True when the lock binary sensor should be on.

    On a live CL6 car, DoorStatus is the lock: ``locked`` or ``unlocked``.
    It does not say whether a door is ajar. Locked is off. Unlocked is on.
    Open and closed words are still accepted for the same on and off.
    """
    if isinstance(value, bool):
        return value
    text = _text(value)
    if text is None:
        return None
    normalized = text.lower()
    if normalized in _LOCKED or normalized in _CLOSED or normalized in _OFF:
        return False
    if normalized in _UNLOCKED or normalized in _OPEN or normalized in _ON:
        return True
    return None


def parse_locked(value: Any, assumed: bool | None) -> bool | None:
    """True when the doors are locked.

    Only the words locked and unlocked are trusted. A successful lock or
    unlock from this integration fills in when the service uses another word.
    """
    text = _text(value)
    if text is not None:
        normalized = text.lower()
        if normalized in _LOCKED:
            return True
        if normalized in _UNLOCKED:
            return False
    return assumed


def parse_gps_time(value: Any) -> datetime | None:
    """Parse common telematics timestamps as UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        stamp = float(value)
        if stamp > 10_000_000_000:
            stamp = stamp / 1000.0
        try:
            return datetime.fromtimestamp(stamp, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    text = _text(value)
    if text is None:
        return None
    match = _DOTNET_DATE_RE.search(text)
    if match:
        return parse_gps_time(int(match.group(1)))
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S%z"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_coordinates(
    latitude: Any, longitude: Any, gps_status: Any
) -> tuple[float | None, float | None]:
    """Return a usable fix, or (None, None) when CL6 has no position."""
    if gps_status is False:
        return None, None
    status_text = _text(gps_status)
    if status_text is not None and status_text.lower() in _NO_FIX:
        return None, None
    lat = parse_float(latitude)
    lon = parse_float(longitude)
    if lat is None or lon is None:
        return None, None
    if lat == 0 and lon == 0:
        return None, None
    if abs(lat) > 90 or abs(lon) > 180:
        return None, None
    return lat, lon


def vehicle_from_status(raw: dict[str, Any] | None, assumed_lock: bool | None) -> dict[str, Any]:
    """Map one DeviceStatus payload onto Cl6Data vehicle fields."""
    raw = raw or {}
    latitude, longitude = parse_coordinates(
        raw.get("Latitude"), raw.get("Longitude"), raw.get("GpsStatus")
    )
    gps_raw = raw.get("GpsDateTime")
    return {
        "latitude": latitude,
        "longitude": longitude,
        "speed": parse_speed(raw.get("Speed")),
        "heading": parse_float(raw.get("Heading")),
        "voltage": parse_float(raw.get("ExternalVoltage")),
        "rssi": parse_float(raw.get("Rssi")),
        "gps_time": parse_gps_time(gps_raw),
        "gps_time_raw": raw_value(gps_raw),
        "gps_status": raw_value(raw.get("GpsStatus")),
        "engine_on": parse_engine(raw.get("EngineStatus")),
        "ignition_on": parse_ignition(raw.get("IgnitionStatus")),
        "doors_open": parse_doors_open(raw.get("DoorStatus")),
        "online": parse_online(raw.get("Online")),
        "locked": parse_locked(raw.get("DoorStatus"), assumed_lock),
        "engine_raw": raw_value(raw.get("EngineStatus")),
        "ignition_raw": raw_value(raw.get("IgnitionStatus")),
        "door_raw": raw_value(raw.get("DoorStatus")),
        "online_raw": raw_value(raw.get("Online")),
        "engine_shutdown_raw": raw_value(raw.get("EngineShutdownDateTime")),
    }
