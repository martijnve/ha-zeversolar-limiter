"""Price threshold below which Auto curtails."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ZeversolarConfigEntry
from .controller import Curtailer
from .entity import ZeversolarEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZeversolarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the threshold number."""
    async_add_entities([PriceThreshold(entry, entry.runtime_data.curtailer)])


class PriceThreshold(ZeversolarEntity, RestoreNumber):
    """Auto curtails while the price is strictly below this. Kept across restarts."""

    _attr_native_min_value = -1.0
    _attr_native_max_value = 1.0
    _attr_native_step = 0.001
    _attr_native_unit_of_measurement = "€/kWh"
    _attr_mode = NumberMode.BOX

    def __init__(self, entry: ZeversolarConfigEntry, curtailer: Curtailer) -> None:
        """Threshold number of the inverter."""
        super().__init__(entry, "price_threshold")
        self._curtailer = curtailer

    async def async_added_to_hass(self) -> None:
        """Restore the threshold (quietly: the first apply comes after setup)."""
        await super().async_added_to_hass()
        if (
            last := await self.async_get_last_number_data()
        ) and last.native_value is not None:
            self._curtailer.threshold = last.native_value

    @property
    def native_value(self) -> float:
        """The threshold."""
        return self._curtailer.threshold

    async def async_set_native_value(self, value: float) -> None:
        """Change the threshold."""
        self._curtailer.set_threshold(value)
        self.async_write_ha_state()
