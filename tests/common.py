"""Values shared by the CL6 tests."""

from __future__ import annotations

from custom_components.cl6.const import DOMAIN

EMAIL = "dylan@example.com"
PASSWORD = "s3cret-password"


def entity_id(hass, domain: str, unique_suffix: str) -> str:
    from homeassistant.helpers import entity_registry as er

    found = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"42:7_{unique_suffix}")
    assert found is not None, unique_suffix
    return found
