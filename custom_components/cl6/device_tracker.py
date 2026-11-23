"""GPS device tracker."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import Cl6Coordinator
from .entity import Cl6Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Cl6Coordinator = hass.data[DOMAIN]["entries"][entry.entry_id]
    async_add_entities([Cl6Tracker(coordinator)])


class Cl6Tracker(Cl6Entity, TrackerEntity):
    """Where the car last reported it was."""

    _attr_translation_key = "location"
    _attr_icon = "mdi:car"

    def __init__(self, coordinator: Cl6Coordinator) -> None:
        super().__init__(coordinator, "location")

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.latitude

    @property
    def longitude(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.longitude

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "speed": data.speed,
            "heading": data.heading,
            "gps_status": data.gps_status,
        }
