"""Polls the inverter's status and power limit."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Limit, Status, ZeversolarClient, ZeversolarError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class InverterData:
    """One poll."""

    status: Status
    limit: Limit


class ZeversolarCoordinator(DataUpdateCoordinator[InverterData]):
    """Every 30 s; unreachable (e.g. at night, when the module has no power) makes entities unavailable.

    DataUpdateCoordinator logs the first failure and the recovery, not every failed poll.
    """

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: ZeversolarClient
    ) -> None:
        """Poll `client`."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> InverterData:
        try:
            return InverterData(
                status=await self.client.status(), limit=await self.client.limit()
            )
        except ZeversolarError as err:
            raise UpdateFailed(str(err)) from err

    def set_limit(self, limit: Limit) -> None:
        """Publish a limit read back after a write, without waiting for the next poll."""
        if self.data is not None:
            self.async_set_updated_data(
                InverterData(status=self.data.status, limit=limit)
            )
