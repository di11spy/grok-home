"""Voltage, signal, GPS time, and the last command."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import Cl6Coordinator
from .entity import Cl6Entity

SENSORS = (
    SensorEntityDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:car-battery",
    ),
    SensorEntityDescription(
        key="signal",
        translation_key="signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:signal",
    ),
    SensorEntityDescription(
        key="gps_time",
        translation_key="gps_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:map-clock",
    ),
    SensorEntityDescription(
        key="last_command",
        translation_key="last_command",
        icon="mdi:history",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Cl6Coordinator = hass.data[DOMAIN]["entries"][entry.entry_id]
    async_add_entities(Cl6Sensor(coordinator, description) for description in SENSORS)


class Cl6Sensor(Cl6Entity, SensorEntity):
    """One numeric or text reading."""

    def __init__(self, coordinator: Cl6Coordinator, description: SensorEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        data = self.coordinator.data
        if data is None:
            return None
        key = self.entity_description.key
        if key == "voltage":
            return data.voltage
        if key == "signal":
            return data.rssi
        if key == "gps_time":
            return data.gps_time
        if data.last_command and data.last_result:
            return f"{data.last_command}: {data.last_result}"
        return "idle"

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if data is None or self.entity_description.key != "last_command":
            if data is not None and self.entity_description.key == "gps_time":
                return {"raw": data.gps_time_raw}
            return {}
        return {
            "command": data.last_command,
            "result": data.last_result,
            "source": data.last_source,
            "command_id": data.last_command_id,
            "at": None if data.last_command_at is None else data.last_command_at.isoformat(),
            "pending_command_id": data.pending_command_id,
            "confirmation": data.arm_action,
        }
