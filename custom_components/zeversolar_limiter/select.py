"""Curtailment mode: Auto (price) / Off / Forced."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import ZeversolarConfigEntry
from .const import Mode
from .controller import Curtailer
from .entity import ZeversolarEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZeversolarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the mode select."""
    async_add_entities([CurtailmentSelect(entry, entry.runtime_data.curtailer)])


class CurtailmentSelect(ZeversolarEntity, SelectEntity, RestoreEntity):
    """The curtailer's mode, kept across restarts. Available while the inverter is offline."""

    _attr_options = [mode.value for mode in Mode]

    def __init__(self, entry: ZeversolarConfigEntry, curtailer: Curtailer) -> None:
        """Mode select of the inverter."""
        super().__init__(entry, "curtailment")
        self._curtailer = curtailer

    async def async_added_to_hass(self) -> None:
        """Restore the mode (quietly: the first apply comes after setup)."""
        await super().async_added_to_hass()
        if (
            last := await self.async_get_last_state()
        ) and last.state in self._attr_options:
            self._curtailer.mode = Mode(last.state)

    @property
    def current_option(self) -> str:
        """The mode."""
        return self._curtailer.mode.value

    async def async_select_option(self, option: str) -> None:
        """Switch mode."""
        self._curtailer.set_mode(Mode(option))
        self.async_write_ha_state()
