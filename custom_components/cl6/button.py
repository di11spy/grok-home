"""Remote start, stop, and confirm buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTION_START, ACTION_STOP, DOMAIN, SOURCE_BUTTON
from .coordinator import Cl6Coordinator
from .entity import Cl6Entity

BUTTONS = (
    ButtonEntityDescription(
        key="start",
        translation_key="start",
        icon="mdi:engine-outline",
    ),
    ButtonEntityDescription(
        key="stop",
        translation_key="stop",
        icon="mdi:engine-off-outline",
    ),
    ButtonEntityDescription(
        key="confirm",
        translation_key="confirm",
        icon="mdi:check-decagram",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Cl6Coordinator = hass.data[DOMAIN]["entries"][entry.entry_id]
    async_add_entities(Cl6Button(coordinator, description) for description in BUTTONS)


class Cl6Button(Cl6Entity, ButtonEntity):
    """A dashboard control for one CL6 action."""

    def __init__(self, coordinator: Cl6Coordinator, description: ButtonEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        key = self.entity_description.key
        if key == "start":
            await self.coordinator.async_arm(ACTION_START, SOURCE_BUTTON)
        elif key == "stop":
            await self.coordinator.async_execute(ACTION_STOP, SOURCE_BUTTON)
        else:
            await self.coordinator.async_confirm(SOURCE_BUTTON)
