"""Confirmation, timers, and the rule that a command is never sent twice."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path

import pytest
from custom_components.cl6.client import Cl6AuthError
from custom_components.cl6.const import CONF_EXTEND_ONCE, DOMAIN
from custom_components.cl6.sentences_setup import async_install_sentences
from homeassistant.const import EVENT_LOGBOOK_ENTRY
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import intent
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from tests.common import EMAIL, PASSWORD, entity_id

pytestmark = pytest.mark.usefixtures("enable_cl6", "cl6_entry")


def _coordinator(hass, entry):
    return hass.data[DOMAIN]["entries"][entry.entry_id]


async def _flush(hass) -> None:
    for _ in range(4):
        await hass.async_block_till_done()


async def _arm_and_confirm(hass) -> None:
    await hass.services.async_call("cl6", "arm", {"action": "start"}, blocking=True)
    await hass.services.async_call("cl6", "confirm", {}, blocking=True)
    await _flush(hass)


async def test_entities_and_voice_phrases(hass, cl6_entry, fake_cl6):
    from homeassistant.helpers import entity_registry as er

    entries = er.async_entries_for_config_entry(er.async_get(hass), cl6_entry.entry_id)
    assert len(entries) == 13
    assert hass.states.get(entity_id(hass, "sensor", "voltage")).state == "12.4"
    assert float(hass.states.get(entity_id(hass, "sensor", "signal")).state) == -70
    assert hass.states.get(entity_id(hass, "binary_sensor", "engine")).state == "off"
    assert hass.states.get(entity_id(hass, "binary_sensor", "online")).state == "on"
    assert hass.states.get(entity_id(hass, "sensor", "last_command")).state == "idle"
    tracker = hass.states.get(entity_id(hass, "device_tracker", "location"))
    assert tracker.attributes["latitude"] == 47.6062
    assert tracker.attributes["speed"] == 0
    doors = hass.states.get(entity_id(hass, "binary_sensor", "doors"))
    assert doors.attributes["raw"] == "Closed"

    phrases_path = Path(hass.config.path("custom_sentences", "en", "cl6.yaml"))
    phrases_path.unlink(missing_ok=True)
    await async_install_sentences(hass)
    phrases = phrases_path.read_text()
    assert "start her car" in phrases
    assert phrases.startswith("# cl6-managed-sentences")

    phrases_path.write_text("language: en\n")
    await async_install_sentences(hass)
    assert phrases_path.read_text() == "language: en\n"
    phrases_path.unlink(missing_ok=True)


async def test_start_needs_confirm_and_confirm_is_single_use(hass, fake_cl6):
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "start")},
        blocking=True,
    )
    assert fake_cl6.submits == []
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "confirm")},
        blocking=True,
    )
    assert fake_cl6.submits == ["EngineStart"]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("cl6", "confirm", {}, blocking=True)
    assert fake_cl6.submits == ["EngineStart"]
    assert hass.states.get(entity_id(hass, "sensor", "last_command")).state == "start: success"


async def test_expired_arm_sends_nothing(hass, fake_cl6):
    await hass.services.async_call("cl6", "arm", {"action": "start"}, blocking=True)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await _flush(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("cl6", "confirm", {}, blocking=True)
    assert fake_cl6.submits == []


async def test_stop_and_lock_do_not_need_confirmation(hass, fake_cl6):
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "stop")},
        blocking=True,
    )
    await hass.services.async_call(
        "lock",
        "lock",
        {"entity_id": entity_id(hass, "lock", "lock")},
        blocking=True,
    )
    assert fake_cl6.submits == ["EngineStop", "DoorLock"]
    assert hass.states.get(entity_id(hass, "lock", "lock")).state == "locked"


async def test_unlock_is_gated(hass, fake_cl6):
    await hass.services.async_call(
        "lock",
        "unlock",
        {"entity_id": entity_id(hass, "lock", "lock")},
        blocking=True,
    )
    assert fake_cl6.submits == []
    lock_state = hass.states.get(entity_id(hass, "lock", "lock"))
    assert lock_state.attributes["unlock_armed"] is True
    await hass.services.async_call("cl6", "confirm", {}, blocking=True)
    assert fake_cl6.submits == ["DoorUnLock"]
    assert hass.states.get(entity_id(hass, "lock", "lock")).state == "unlocked"


async def test_pending_command_is_not_sent_again(hass, cl6_entry, fake_cl6):
    fake_cl6.next_command_status = "Pending"
    await _arm_and_confirm(hass)
    assert fake_cl6.submits == ["EngineStart"]
    assert hass.states.get(entity_id(hass, "sensor", "last_command")).state == "start: unknown"

    await _coordinator(hass, cl6_entry).async_refresh()
    await _flush(hass)
    assert fake_cl6.submits == ["EngineStart"]

    fake_cl6.next_command_status = "Success"
    await _coordinator(hass, cl6_entry).async_refresh()
    await _flush(hass)
    assert fake_cl6.submits == ["EngineStart"]
    assert hass.states.get(entity_id(hass, "sensor", "last_command")).state == "start: success"


async def test_submit_timeout_is_unknown_and_the_timer_stops_once(hass, fake_cl6):
    fake_cl6.fail_submit = "timeout"
    await _arm_and_confirm(hass)
    assert fake_cl6.submits == ["EngineStart"]
    assert hass.states.get(entity_id(hass, "sensor", "last_command")).state == "start: unknown"

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1, seconds=5))
    await _flush(hass)
    assert fake_cl6.submits == ["EngineStart", "EngineStop"]


async def test_speed_above_zero_stops_only_our_remote_start(hass, cl6_entry, fake_cl6):
    fake_cl6.status["Speed"] = 30
    await _coordinator(hass, cl6_entry).async_refresh()
    await _flush(hass)
    assert fake_cl6.submits == []

    fake_cl6.status["Speed"] = 0
    await _coordinator(hass, cl6_entry).async_refresh()
    await _arm_and_confirm(hass)
    assert fake_cl6.submits == ["EngineStart"]

    fake_cl6.status["Speed"] = 4
    await _coordinator(hass, cl6_entry).async_refresh()
    await _flush(hass)
    assert fake_cl6.submits == ["EngineStart", "EngineStop"]

    fake_cl6.status["Speed"] = 8
    await _coordinator(hass, cl6_entry).async_refresh()
    await _flush(hass)
    assert fake_cl6.submits == ["EngineStart", "EngineStop"]


async def test_max_run_sends_one_stop(hass, fake_cl6):
    await _arm_and_confirm(hass)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1, seconds=5))
    await _flush(hass)
    assert fake_cl6.submits == ["EngineStart", "EngineStop"]
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1, seconds=5))
    await _flush(hass)
    assert fake_cl6.submits == ["EngineStart", "EngineStop"]


async def test_extend_once_starts_again_then_stops(hass, cl6_entry, fake_cl6):
    hass.config_entries.async_update_entry(
        cl6_entry,
        options={**cl6_entry.options, CONF_EXTEND_ONCE: True},
    )
    await _flush(hass)
    await _arm_and_confirm(hass)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1, seconds=5))
    await _flush(hass)
    assert fake_cl6.submits == ["EngineStart", "EngineStart"]
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1, seconds=5))
    await _flush(hass)
    assert fake_cl6.submits == ["EngineStart", "EngineStart", "EngineStop"]


async def test_auth_failure_retries_login_once_then_asks_again(hass, cl6_entry, fake_cl6):
    fake_cl6.auth_failures = 1
    await _coordinator(hass, cl6_entry).async_refresh()
    await _flush(hass)
    assert fake_cl6.relogins == 1
    assert _coordinator(hass, cl6_entry).last_update_success
    assert not [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"]["source"] == "reauth"
    ]

    fake_cl6.auth_failures = 2
    await _coordinator(hass, cl6_entry).async_refresh()
    await _flush(hass)
    assert not _coordinator(hass, cl6_entry).last_update_success
    sources = [flow["context"]["source"] for flow in hass.config_entries.flow.async_progress()]
    assert "reauth" in sources


async def test_logs_and_events_omit_credentials(hass, fake_cl6, caplog):
    caplog.set_level(logging.DEBUG)
    events = []
    hass.bus.async_listen(EVENT_LOGBOOK_ENTRY, lambda event: events.append(event))
    hass.bus.async_listen("cl6_command", lambda event: events.append(event))
    await _arm_and_confirm(hass)
    blob = json.dumps([event.data for event in events], default=str)
    blob += "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("custom_components.cl6")
    )
    assert PASSWORD not in blob
    assert EMAIL not in blob
    assert any(event.data.get("message", "").startswith("Sent remote start") for event in events)
    assert any(event.data.get("result") == "success" for event in events)


async def test_assist_start_asks_for_confirm(hass, fake_cl6):
    armed = await intent.async_handle(hass, "test", "Cl6ArmStart", {})
    assert "confirm" in armed.speech["plain"]["speech"].lower()
    assert fake_cl6.submits == []
    confirmed = await intent.async_handle(hass, "test", "Cl6Confirm", {})
    assert fake_cl6.submits == ["EngineStart"]
    assert "accepted" in confirmed.speech["plain"]["speech"].lower()
    stopped = await intent.async_handle(hass, "test", "Cl6Stop", {})
    assert fake_cl6.submits[-1] == "EngineStop"
    assert "accepted" in stopped.speech["plain"]["speech"].lower()


async def test_saved_login_rejection_starts_reauth(hass, mock_connect):
    mock_connect.connect_error = Cl6AuthError("rejected")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "email": EMAIL,
            "password": PASSWORD,
            "account_id": 42,
            "asset_id": 7,
            "vehicle_name": "Her Car",
        },
        unique_id="42:7",
        title="Her Car",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id) is False
    await _flush(hass)
    sources = [flow["context"]["source"] for flow in hass.config_entries.flow.async_progress()]
    assert "reauth" in sources
