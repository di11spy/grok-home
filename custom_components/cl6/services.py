"""Service calls for arm and confirm."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.service import async_extract_config_entry_ids

from .const import ARM_ACTIONS, DOMAIN, SOURCE_SERVICE
from .coordinator import Cl6Coordinator

ARM_SCHEMA = vol.Schema(
    {vol.Required("action"): vol.In(ARM_ACTIONS)},
    extra=vol.ALLOW_EXTRA,
)
CONFIRM_SCHEMA = vol.Schema({}, extra=vol.ALLOW_EXTRA)


def coordinators(hass: HomeAssistant) -> list[Cl6Coordinator]:
    """Return every loaded CL6 car."""
    return list(hass.data.get(DOMAIN, {}).get("entries", {}).values())


async def async_coordinators_for_call(
    hass: HomeAssistant, call: ServiceCall
) -> list[Cl6Coordinator]:
    """Resolve the car a service call is aimed at."""
    loaded = {entry_id: coord for entry_id, coord in hass.data[DOMAIN]["entries"].items()}
    if not loaded:
        raise ServiceValidationError("CL6 is not set up yet.")
    requested = await async_extract_config_entry_ids(hass, call)
    if not requested:
        if len(loaded) == 1:
            return list(loaded.values())
        raise ServiceValidationError("Choose the CL6 car. More than one is set up.")
    found = [loaded[entry_id] for entry_id in requested if entry_id in loaded]
    if not found:
        raise ServiceValidationError("That device is not a CL6 car.")
    return found


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register arm and confirm once."""
    if hass.services.has_service(DOMAIN, "arm"):
        return

    async def _arm(call: ServiceCall) -> None:
        action = call.data["action"]
        for coordinator in await async_coordinators_for_call(hass, call):
            await coordinator.async_arm(action, SOURCE_SERVICE)

    async def _confirm(call: ServiceCall) -> None:
        for coordinator in await async_coordinators_for_call(hass, call):
            await coordinator.async_confirm(SOURCE_SERVICE)

    hass.services.async_register(DOMAIN, "arm", _arm, schema=ARM_SCHEMA)
    hass.services.async_register(DOMAIN, "confirm", _confirm, schema=CONFIRM_SCHEMA)
