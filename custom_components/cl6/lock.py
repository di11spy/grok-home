"""Door lock. Unlock only arms a confirmation."""

from __future__ import annotations

from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTION_LOCK, ACTION_UNLOCK, DOMAIN, SOURCE_LOCK
from .coordinator import Cl6Coordinator
from .entity import Cl6Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Cl6Coordinator = hass.data[DOMAIN]["entries"][entry.entry_id]
    async_add_entities([Cl6Lock(coordinator)])


class Cl6Lock(Cl6Entity, LockEntity):
    """Lock sends immediately. Unlock waits for confirm."""

    entity_description = LockEntityDescription(
        key="doors",
        translation_key="doors",
        icon="mdi:car-door-lock",
    )

    def __init__(self, coordinator: Cl6Coordinator) -> None:
        super().__init__(coordinator, "lock")

    @property
    def is_locked(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.locked

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "raw": data.door_raw,
            "unlock_armed": data.arm_action == ACTION_UNLOCK,
        }

    async def async_lock(self, **kwargs) -> None:
        await self.coordinator.async_execute(ACTION_LOCK, SOURCE_LOCK)

    async def async_unlock(self, **kwargs) -> None:
        await self.coordinator.async_arm(ACTION_UNLOCK, SOURCE_LOCK)
