"""Power, energy today and output limit."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ZeversolarConfigEntry
from .coordinator import InverterData, ZeversolarCoordinator
from .entity import ZeversolarEntity


@dataclass(frozen=True, kw_only=True)
class ZeversolarSensorDescription(SensorEntityDescription):
    """A sensor and how to read it from a poll."""

    value: Callable[[InverterData], float | int]


SENSORS = (
    ZeversolarSensorDescription(
        key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value=lambda data: data.status.power,
    ),
    ZeversolarSensorDescription(
        key="energy_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value=lambda data: data.status.energy_today,
    ),
    ZeversolarSensorDescription(
        key="output_limit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value=lambda data: data.limit.percent,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZeversolarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        ZeversolarSensor(entry, coordinator, description) for description in SENSORS
    )


class ZeversolarSensor(
    ZeversolarEntity, CoordinatorEntity[ZeversolarCoordinator], SensorEntity
):
    """A value from the last poll."""

    entity_description: ZeversolarSensorDescription

    def __init__(
        self,
        entry: ZeversolarConfigEntry,
        coordinator: ZeversolarCoordinator,
        description: ZeversolarSensorDescription,
    ) -> None:
        """Sensor `description` of the inverter."""
        CoordinatorEntity.__init__(self, coordinator)
        ZeversolarEntity.__init__(self, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | None:
        """The value, None before the first successful poll."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value(self.coordinator.data)
