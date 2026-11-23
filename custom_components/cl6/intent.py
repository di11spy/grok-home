"""Assist intents. Sentences live in sentences/en/cl6.yaml."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import intent

from .const import (
    ACTION_LOCK,
    ACTION_START,
    ACTION_STOP,
    ACTION_UNLOCK,
    DOMAIN,
    RESULT_FAILED,
    RESULT_SUCCESS,
    RESULT_UNKNOWN,
    SOURCE_ASSIST,
)
from .services import coordinators

INTENT_ARM_START = "Cl6ArmStart"
INTENT_ARM_UNLOCK = "Cl6ArmUnlock"
INTENT_CONFIRM = "Cl6Confirm"
INTENT_STOP = "Cl6Stop"
INTENT_LOCK = "Cl6Lock"


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Register intent handlers. Safe to call more than once."""
    bucket = hass.data.setdefault(DOMAIN, {})
    if bucket.get("intents_ready"):
        return
    bucket["intents_ready"] = True
    intent.async_register(hass, _ArmIntent(INTENT_ARM_START, ACTION_START))
    intent.async_register(hass, _ArmIntent(INTENT_ARM_UNLOCK, ACTION_UNLOCK))
    intent.async_register(hass, _ConfirmIntent())
    intent.async_register(hass, _ImmediateIntent(INTENT_STOP, ACTION_STOP))
    intent.async_register(hass, _ImmediateIntent(INTENT_LOCK, ACTION_LOCK))


def _single(hass: HomeAssistant):
    cars = coordinators(hass)
    if not cars:
        return None, "CL6 is not set up yet."
    if len(cars) > 1:
        return None, "More than one CL6 car is set up. Use the dashboard to pick the car."
    return cars[0], None


def _speech(intent_obj: intent.Intent, text: str) -> intent.IntentResponse:
    response = intent_obj.create_response()
    response.async_set_speech(text)
    return response


class _ArmIntent(intent.IntentHandler):
    """Arm a start or unlock and ask for the word confirm."""

    def __init__(self, intent_type: str, action: str) -> None:
        self.intent_type = intent_type
        self._action = action
        if action == ACTION_START:
            self.description = (
                "Arm a CL6 remote start. Nothing is sent until the user says confirm."
            )
        else:
            self.description = "Arm a CL6 unlock. Nothing is sent until the user says confirm."

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        coordinator, problem = _single(intent_obj.hass)
        if problem:
            return _speech(intent_obj, problem)
        await coordinator.async_arm(self._action, SOURCE_ASSIST)
        if self._action == ACTION_START:
            text = "Remote start is armed. Say confirm to start the car."
        else:
            text = "Unlock is armed. Say confirm to unlock the car."
        return _speech(intent_obj, text)


class _ConfirmIntent(intent.IntentHandler):
    """Send the armed start or unlock."""

    intent_type = INTENT_CONFIRM
    description = "Confirm an armed CL6 remote start or unlock."

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        coordinator, problem = _single(intent_obj.hass)
        if problem:
            return _speech(intent_obj, problem)
        try:
            result = await coordinator.async_confirm(SOURCE_ASSIST)
        except ServiceValidationError as err:
            return _speech(intent_obj, str(err))
        action = coordinator.data.last_command if coordinator.data else "command"
        return _speech(intent_obj, _result_speech(action, result))


class _ImmediateIntent(intent.IntentHandler):
    """Stop or lock without a confirmation step."""

    def __init__(self, intent_type: str, action: str) -> None:
        self.intent_type = intent_type
        self._action = action
        if action == ACTION_STOP:
            self.description = "Stop the CL6 car's engine."
        else:
            self.description = "Lock the CL6 car."

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        coordinator, problem = _single(intent_obj.hass)
        if problem:
            return _speech(intent_obj, problem)
        result = await coordinator.async_execute(self._action, SOURCE_ASSIST)
        return _speech(intent_obj, _result_speech(self._action, result))


def _result_speech(action: str | None, result: str) -> str:
    name = {
        ACTION_START: "start",
        ACTION_STOP: "stop",
        ACTION_LOCK: "lock",
        ACTION_UNLOCK: "unlock",
    }.get(action or "", "command")
    if result == RESULT_SUCCESS:
        return f"The car accepted the {name}."
    if result == RESULT_FAILED:
        return f"The {name} did not go through."
    if result == RESULT_UNKNOWN:
        return (
            f"The {name} was sent, but CL6 did not confirm it. "
            "It will not be sent again. Check the car."
        )
    return f"The {name} finished with result {result}."
