"""Install English Assist phrases into Home Assistant's sentence folder.

Home Assistant reads config/custom_sentences/<language>/*.yaml. A file inside
the integration is not picked up on its own, so setup copies the bundled
phrases into that folder.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import SENTENCE_MARKER

_LOGGER = logging.getLogger(__name__)
_SOURCE = Path(__file__).parent / "sentences" / "en" / "cl6.yaml"


async def async_install_sentences(hass: HomeAssistant) -> None:
    """Copy bundled phrases unless someone has edited the destination."""
    content = _SOURCE.read_text(encoding="utf-8")
    destination = Path(hass.config.path("custom_sentences", "en", "cl6.yaml"))

    def _write() -> str:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            existing = destination.read_text(encoding="utf-8")
            first_lines = existing.splitlines()[:3]
            if SENTENCE_MARKER not in first_lines:
                return "kept"
            if existing == content:
                return "same"
        destination.write_text(content, encoding="utf-8")
        return "wrote"

    try:
        result = await hass.async_add_executor_job(_write)
    except OSError:
        _LOGGER.warning("CL6 could not install voice phrases.")
        return

    if result == "kept":
        _LOGGER.info("CL6 left the existing voice phrase file alone.")
        return
    if result == "wrote" and hass.services.has_service("conversation", "reload"):
        await hass.services.async_call("conversation", "reload", {}, blocking=True)
