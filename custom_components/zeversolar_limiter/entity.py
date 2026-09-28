"""Device info shared by all entities."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

CONF_HARDWARE = "hardware"
CONF_SOFTWARE = "software"


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """The inverter, from what the config flow read (so it exists while the inverter is offline)."""
    assert entry.unique_id is not None
    return DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id)},
        name="Zeversolar inverter",
        manufacturer="Zeversolar",
        model=entry.data.get(CONF_HARDWARE),
        sw_version=entry.data.get(CONF_SOFTWARE),
        serial_number=entry.unique_id,
        configuration_url=f"http://{entry.data[CONF_HOST]}/",
    )


class ZeversolarEntity(Entity):
    """Named after its translation key, on the inverter device."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, key: str) -> None:
        """Entity `key` of the inverter of `entry`."""
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = device_info(entry)
