"""Whether the inverter is curtailed right now."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ZeversolarConfigEntry
from .controller import Curtailer
from .coordinator import ZeversolarCoordinator
from .entity import ZeversolarEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZeversolarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the curtailing sensor."""
    data = entry.runtime_data
    async_add_entities([CurtailingSensor(entry, data.coordinator, data.curtailer)])


class CurtailingSensor(
    ZeversolarEntity, CoordinatorEntity[ZeversolarCoordinator], BinarySensorEntity
):
    """On while the inverter's limit is below 100 %, as read back from the inverter.

    `reason` says why the integration wants it curtailed (price / forced), None when it doesn't.
    """

    def __init__(
        self,
        entry: ZeversolarConfigEntry,
        coordinator: ZeversolarCoordinator,
        curtailer: Curtailer,
    ) -> None:
        """Curtailing sensor of the inverter."""
        CoordinatorEntity.__init__(self, coordinator)
        ZeversolarEntity.__init__(self, entry, "curtailing")
        self._curtailer = curtailer

    async def async_added_to_hass(self) -> None:
        """Also follow the curtailer's reason."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._curtailer.async_add_listener(self.async_write_ha_state)
        )

    @property
    def is_on(self) -> bool | None:
        """Curtailed, None before the first successful poll."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.limit.percent < 100

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Why."""
        reason = self._curtailer.reason
        return {"reason": reason.value if reason else None}
