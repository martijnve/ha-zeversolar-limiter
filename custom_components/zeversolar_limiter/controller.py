"""Decides whether the inverter should be curtailed and makes it so."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.event import async_track_state_change_event

from .api import ZeversolarError
from .const import CURTAILED_PERCENT, Mode, Reason
from .coordinator import ZeversolarCoordinator

_LOGGER = logging.getLogger(__name__)


class Curtailer:
    """Owns the inverter's power limit.

    Wanted: Forced → curtailed, Off → full output, Auto → curtailed while the price is below the
    threshold. An unavailable price means full output. Evaluated when the price, the mode or the
    threshold changes and after every poll; it writes only when the inverter differs from what is
    wanted, so a limit lost when the inverter restarts at sunrise is re-applied on the first poll.
    """

    def __init__(
        self, hass: HomeAssistant, coordinator: ZeversolarCoordinator, price_entity: str
    ) -> None:
        """Curtail the inverter behind `coordinator` on the price in `price_entity`."""
        self.hass = hass
        self.coordinator = coordinator
        self.price_entity = price_entity
        self.mode = Mode.AUTO
        self.threshold = 0.0
        self.reason: Reason | None = None
        self._listeners: list[Callable[[], None]] = []
        self._lock = asyncio.Lock()
        self._price_missing = False

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Start following the price and the polls; returns the stop callback."""
        unsubs = [
            async_track_state_change_event(
                self.hass, self.price_entity, self._price_changed
            ),
            self.coordinator.async_add_listener(self.async_schedule),
        ]
        self.async_schedule()

        @callback
        def stop() -> None:
            for unsub in unsubs:
                unsub()

        return stop

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        """Call `update` when the reason changes."""
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def set_mode(self, mode: Mode) -> None:
        """Change the mode and re-evaluate."""
        self.mode = mode
        self.async_schedule()

    @callback
    def set_threshold(self, threshold: float) -> None:
        """Change the price threshold and re-evaluate."""
        self.threshold = threshold
        self.async_schedule()

    @callback
    def async_schedule(self) -> None:
        """Re-evaluate in the background."""
        self.coordinator.config_entry.async_create_background_task(
            self.hass, self.async_apply(), "zeversolar_limiter apply"
        )

    def price(self) -> float | None:
        """The current price, or None when it isn't a number."""
        state = self.hass.states.get(self.price_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def wanted(self) -> Reason | None:
        """Why the inverter should be curtailed, or None for full output."""
        if self.mode is Mode.FORCED:
            return Reason.FORCED
        if self.mode is Mode.OFF:
            return None
        price = self.price()
        if price is None:
            if not self._price_missing:
                _LOGGER.warning("%s has no price; not curtailing", self.price_entity)
            self._price_missing = True
            return None
        self._price_missing = False
        return Reason.PRICE if price < self.threshold else None

    async def async_apply(self) -> None:
        """Bring the inverter in line with what is wanted."""
        async with self._lock:
            reason = self.wanted()
            if reason != self.reason:
                self.reason = reason
                for update in list(self._listeners):
                    update()

            data = self.coordinator.data
            if data is None or not self.coordinator.last_update_success:
                return  # offline: the first successful poll re-runs this
            curtail = reason is not None
            if curtail and data.limit.percent == CURTAILED_PERCENT:
                return
            if not curtail and not data.limit.enabled:
                return

            client = self.coordinator.client
            try:
                limit = await (
                    client.set_limit(CURTAILED_PERCENT)
                    if curtail
                    else client.clear_limit()
                )
            except ZeversolarError as err:
                _LOGGER.warning(
                    "Could not %s: %s", "curtail" if curtail else "clear the limit", err
                )
                return
            if curtail:
                _LOGGER.info(
                    "Curtailed to %s %% (%s, price %s)",
                    CURTAILED_PERCENT,
                    reason,
                    self.price(),
                )
            else:
                _LOGGER.info(
                    "Limit cleared (mode %s, price %s)", self.mode, self.price()
                )
            self.coordinator.set_limit(limit)

    @callback
    def _price_changed(self, event: Event[EventStateChangedData]) -> None:
        self.async_schedule()
