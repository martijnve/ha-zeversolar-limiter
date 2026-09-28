"""Zeversolar Limiter: a local Zeversolar inverter that curtails itself when energy is cheap."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZeversolarClient, ZeversolarError
from .const import CONF_PRICE_ENTITY, DEFAULT_PRICE_ENTITY
from .controller import Curtailer
from .coordinator import ZeversolarCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SELECT, Platform.SENSOR]


@dataclass
class RuntimeData:
    """What the platforms share."""

    coordinator: ZeversolarCoordinator
    curtailer: Curtailer


type ZeversolarConfigEntry = ConfigEntry[RuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: ZeversolarConfigEntry) -> bool:
    """Set up the inverter; an offline inverter (night) doesn't block setup."""
    client = ZeversolarClient(async_get_clientsession(hass), entry.data[CONF_HOST])
    coordinator = ZeversolarCoordinator(hass, entry, client)
    await coordinator.async_refresh()
    curtailer = Curtailer(
        hass, coordinator, entry.options.get(CONF_PRICE_ENTITY, DEFAULT_PRICE_ENTITY)
    )
    entry.runtime_data = RuntimeData(coordinator, curtailer)

    # The select and number restore the mode and threshold while being added, before the first apply.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(curtailer.async_start())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZeversolarConfigEntry) -> bool:
    """Unload; the inverter keeps whatever limit it has."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ZeversolarConfigEntry) -> None:
    """Removed: give the inverter its full output back."""
    client = ZeversolarClient(async_get_clientsession(hass), entry.data[CONF_HOST])
    try:
        await client.clear_limit()
    except ZeversolarError as err:
        _LOGGER.warning(
            "Could not clear the inverter's power limit on removal: %s", err
        )
