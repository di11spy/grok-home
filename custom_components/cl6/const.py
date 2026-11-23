"""Constants for the CL6 remote start integration."""

from __future__ import annotations

DOMAIN = "cl6"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_ACCOUNT_ID = "account_id"
CONF_ASSET_ID = "asset_id"
CONF_VEHICLE_NAME = "vehicle_name"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_MAX_RUN_MINUTES = "max_run_minutes"
CONF_EXTEND_ONCE = "extend_once"
CONF_CONFIRM_SECONDS = "confirm_seconds"

DEFAULT_SCAN_INTERVAL = 5
MIN_SCAN_INTERVAL = 2
MAX_SCAN_INTERVAL = 60

DEFAULT_MAX_RUN_MINUTES = 10
MIN_MAX_RUN_MINUTES = 1
MAX_MAX_RUN_MINUTES = 30

DEFAULT_CONFIRM_SECONDS = 30
MIN_CONFIRM_SECONDS = 10
MAX_CONFIRM_SECONDS = 180

ACTION_START = "start"
ACTION_STOP = "stop"
ACTION_LOCK = "lock"
ACTION_UNLOCK = "unlock"

ARM_ACTIONS = (ACTION_START, ACTION_UNLOCK)

# M2M Suite command names. Unlock is spelled DoorUnLock by the service.
API_COMMANDS = {
    ACTION_START: "EngineStart",
    ACTION_STOP: "EngineStop",
    ACTION_LOCK: "DoorLock",
    ACTION_UNLOCK: "DoorUnLock",
}

RESULT_SUCCESS = "success"
RESULT_FAILED = "failed"
RESULT_UNKNOWN = "unknown"

PENDING_STATUSES = frozenset({"Pending", "Processing"})
SUCCESS_STATUS = "Success"

POLL_ATTEMPTS = 2
POLL_DELAY_SECONDS = 10

MANUFACTURER = "MyCarControls"
MODEL = "CL6"

EVENT_COMMAND = "cl6_command"
SENTENCE_MARKER = "# cl6-managed-sentences"

SOURCE_BUTTON = "button"
SOURCE_LOCK = "lock"
SOURCE_SERVICE = "service"
SOURCE_ASSIST = "assist"
SOURCE_MAX_RUN = "max_run_time"
SOURCE_EXTEND = "extend"
SOURCE_SPEED = "speed"
