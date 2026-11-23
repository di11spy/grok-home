"""Engine, ignition, doors, and online."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import Cl6Coordinator
from .entity import Cl6Entity
from .models import Cl6Data


@dataclass(frozen=True, kw_only=True)
class Cl6BinaryDescription(BinarySensorEntityDescription):
    """Binary sensor plus how to read it."""

    is_on_fn: Callable[[Cl6Data], bool | None]
    raw_fn: Callable[[Cl6Data], str | None]


SENSORS = (
    Cl6BinaryDescription(
        key="engine",
        translation_key="engine",
        device_class=BinarySensorDeviceClass.RUNNING,
        is_on_fn=lambda data: data.engine_on,
        raw_fn=lambda data: data.engine_raw,
    ),
    Cl6BinaryDescription(
        key="ignition",
        translation_key="ignition",
        device_class=BinarySensorDeviceClass.POWER,
        is_on_fn=lambda data: data.ignition_on,
        raw_fn=lambda data: data.ignition_raw,
    ),
    Cl6BinaryDescription(
        key="doors",
        translation_key="doors",
        device_class=BinarySensorDeviceClass.DOOR,
        is_on_fn=lambda data: data.doors_open,
        raw_fn=lambda data: data.door_raw,
    ),
    Cl6BinaryDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        is_on_fn=lambda data: data.online,
        raw_fn=lambda data: data.online_raw,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Cl6Coordinator = hass.data[DOMAIN]["entries"][entry.entry_id]
    async_add_entities(Cl6BinarySensor(coordinator, description) for description in SENSORS)


class Cl6BinarySensor(Cl6Entity, BinarySensorEntity):
    """One on/off reading from the car."""

    entity_description: Cl6BinaryDescription

    def __init__(self, coordinator: Cl6Coordinator, description: Cl6BinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.is_on_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if data is None:
            return {}
        attributes = {"raw": self.entity_description.raw_fn(data)}
        if self.entity_description.key == "engine":
            attributes["engine_shutdown"] = data.engine_shutdown_raw
        return attributes
