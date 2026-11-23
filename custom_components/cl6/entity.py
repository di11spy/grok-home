"""Shared device info for CL6 entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import Cl6Coordinator


class Cl6Entity(CoordinatorEntity[Cl6Coordinator]):
    """Entity attached to one CL6 car."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: Cl6Coordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_key}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_key)},
            name=coordinator.vehicle_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            configuration_url="https://www.mycarcontrols.com/",
        )
