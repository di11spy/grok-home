"""Status words from CL6 are not a published list. Cover the guesses."""

from datetime import UTC, datetime

from custom_components.cl6.parser import (
    parse_coordinates,
    parse_doors_open,
    parse_engine,
    parse_gps_time,
    parse_locked,
    parse_online,
    parse_speed,
    vehicle_from_status,
)


def test_engine_ignition_and_online_words():
    assert parse_engine("Running") is True
    assert parse_engine("Off") is False
    assert parse_engine("maybe") is None
    assert parse_engine(True) is True
    assert parse_online(1) is True
    assert parse_online("offline") is False


def test_door_status_is_the_lock():
    assert parse_doors_open("locked") is False
    assert parse_doors_open("Locked") is False
    assert parse_doors_open("unlocked") is True
    assert parse_doors_open("Open") is True
    assert parse_doors_open("Closed") is False
    assert parse_doors_open("maybe") is None
    assert parse_locked("locked", None) is True
    assert parse_locked("Unlocked", None) is False
    assert parse_locked("Closed", True) is True
    assert parse_locked("Closed", None) is None


def test_speed_and_coordinates():
    assert parse_speed("0 mph") == 0
    assert parse_speed("3.5 km/h") == 3.5
    assert parse_speed(True) is None
    assert parse_coordinates(0, 0, "Valid") == (None, None)
    assert parse_coordinates(47.6, -122.3, "Invalid") == (None, None)
    assert parse_coordinates(47.6, -122.3, "Valid") == (47.6, -122.3)
    assert parse_coordinates(47.6, -122.3, False) == (None, None)


def test_gps_time_formats():
    parsed = parse_gps_time("2026-01-15T12:30:00Z")
    assert parsed == datetime(2026, 1, 15, 12, 30, tzinfo=UTC)
    assert parse_gps_time("/Date(1736944200000)/") is not None
    assert parse_gps_time("not-a-time") is None


def test_vehicle_snapshot_keeps_raw_text():
    fields = vehicle_from_status(
        {
            "Latitude": 47.6,
            "Longitude": -122.3,
            "Speed": "0",
            "GpsStatus": "Valid",
            "GpsDateTime": "2026-01-15T12:30:00Z",
            "ExternalVoltage": "12.4",
            "Rssi": 84,
            "DoorStatus": "Closed",
            "EngineStatus": "Running",
            "IgnitionStatus": "On",
            "Online": True,
            "EngineShutdownDateTime": "later",
        },
        assumed_lock=None,
    )
    assert fields["engine_on"] is True
    assert fields["ignition_on"] is True
    assert fields["doors_open"] is False
    assert fields["locked"] is None
    assert fields["voltage"] == 12.4
    assert fields["rssi"] == 84
    assert fields["online"] is True
    assert fields["online_raw"] == "true"
    assert fields["engine_raw"] == "Running"
    assert fields["engine_shutdown_raw"] == "later"
    locked = vehicle_from_status({"DoorStatus": "locked", "Online": False}, None)
    assert locked["doors_open"] is False
    assert locked["locked"] is True
    assert locked["door_raw"] == "locked"
    assert locked["online_raw"] == "false"
