"""CL6 / MyCarControls remote start for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from . import client as cl6_client
from .client import Cl6ApiError, Cl6AuthError, Cl6ConnectionError, Cl6Timeout
from .const import CONF_ASSET_ID, CONF_EMAIL, CONF_PASSWORD, DOMAIN
from .coordinator import Cl6Coordinator
from .intent import async_setup_intents
from .sentences_setup import async_install_sentences
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BUTTON,
    Platform.LOCK,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.DEVICE_TRACKER,
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up services, voice phrases, and intent handlers."""
    hass.data.setdefault(DOMAIN, {"entries": {}})
    await async_setup_services(hass)
    await async_setup_intents(hass)
    await async_install_sentences(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Log in and start polling one car."""
    hass.data.setdefault(DOMAIN, {"entries": {}})
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    asset_id = entry.data[CONF_ASSET_ID]

    def _connect():
        return cl6_client.connect(email, password, asset_id=asset_id, load_status=True)

    try:
        client = await hass.async_add_executor_job(_connect)
    except Cl6AuthError:
        _LOGGER.warning("CL6 rejected the saved login.")
        entry.async_start_reauth(hass)
        return False
    except (Cl6ConnectionError, Cl6Timeout, Cl6ApiError):
        raise ConfigEntryNotReady("CL6 is not reachable") from None

    coordinator = Cl6Coordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN]["entries"][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a car."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN]["entries"].pop(entry.entry_id, None)
    return unloaded


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply a new polling interval without cancelling a remote start."""
    coordinator = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry.entry_id)
    if coordinator is not None:
        coordinator.apply_options()
