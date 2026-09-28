"""When the inverter gets curtailed, and that it is written only on a change."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, State
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from .conftest import PRICE, FakeInverter

CURTAILING = "binary_sensor.zeversolar_inverter_curtailing"
MODE = "select.zeversolar_inverter_curtailment"
THRESHOLD = "number.zeversolar_inverter_price_threshold"
LIMIT = "sensor.zeversolar_inverter_output_limit"


async def set_price(hass: HomeAssistant, price: str) -> None:
    """New price, and let the curtailer act on it."""
    hass.states.async_set(PRICE, price)
    await hass.async_block_till_done()


async def poll(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """One coordinator poll."""
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_entities(
    hass: HomeAssistant, entry: MockConfigEntry, inverter: FakeInverter
) -> None:
    """Positive price: nothing written, full output."""
    assert hass.states.get("sensor.zeversolar_inverter_power").state == "846"
    assert hass.states.get("sensor.zeversolar_inverter_energy_today").state == "1.07"
    assert hass.states.get(LIMIT).state == "100"
    assert hass.states.get(CURTAILING).state == "off"
    assert hass.states.get(CURTAILING).attributes["reason"] is None
    assert hass.states.get(MODE).state == "auto"
    assert hass.states.get(THRESHOLD).state == "0.0"
    assert inverter.writes == []


async def test_negative_price(
    hass: HomeAssistant, entry: MockConfigEntry, inverter: FakeInverter
) -> None:
    """Below the threshold: 5 %, once; back above: cleared."""
    await set_price(hass, "-0.01")
    assert inverter.writes == [5]
    assert hass.states.get(CURTAILING).state == "on"
    assert hass.states.get(CURTAILING).attributes["reason"] == "price"
    assert hass.states.get(LIMIT).state == "5"

    await set_price(hass, "-0.02")
    await poll(hass, entry)
    assert inverter.writes == [5]

    await set_price(hass, "0.00")  # not strictly below
    assert inverter.writes == [5, None]
    assert hass.states.get(CURTAILING).state == "off"


async def test_price_unavailable(
    hass: HomeAssistant, entry: MockConfigEntry, inverter: FakeInverter
) -> None:
    """No price means full output."""
    await set_price(hass, "-0.05")
    await set_price(hass, "unavailable")
    assert inverter.writes == [5, None]


async def test_modes_and_threshold(
    hass: HomeAssistant, entry: MockConfigEntry, inverter: FakeInverter
) -> None:
    """Forced curtails whatever the price, Off never, the threshold moves Auto's line."""
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": MODE, "option": "forced"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert inverter.writes == [5]
    assert hass.states.get(CURTAILING).attributes["reason"] == "forced"

    await set_price(hass, "-0.10")
    await hass.services.async_call(
        "select", "select_option", {"entity_id": MODE, "option": "off"}, blocking=True
    )
    await hass.async_block_till_done()
    assert inverter.writes == [5, None]

    await hass.services.async_call(
        "select", "select_option", {"entity_id": MODE, "option": "auto"}, blocking=True
    )
    await hass.async_block_till_done()
    assert inverter.writes == [5, None, 5]

    await hass.services.async_call(
        "number", "set_value", {"entity_id": THRESHOLD, "value": -0.2}, blocking=True
    )
    await hass.async_block_till_done()
    assert inverter.writes == [5, None, 5, None]


async def test_offline_then_back(
    hass: HomeAssistant, entry: MockConfigEntry, inverter: FakeInverter
) -> None:
    """Offline: nothing written, entities unavailable; the first poll after that applies it."""
    inverter.online = False
    await poll(hass, entry)
    assert hass.states.get(CURTAILING).state == "unavailable"
    assert hass.states.get(MODE).state == "auto"
    await set_price(hass, "-0.01")
    assert inverter.writes == []

    inverter.online = True
    await poll(hass, entry)
    assert inverter.writes == [5]
    assert hass.states.get(CURTAILING).state == "on"


async def test_limit_lost_is_reapplied(
    hass: HomeAssistant, entry: MockConfigEntry, inverter: FakeInverter
) -> None:
    """The inverter dropped the limit (restart at sunrise, someone in the web UI)."""
    await set_price(hass, "-0.01")
    inverter.enabled, inverter.percent = False, 100
    await poll(hass, entry)
    assert inverter.writes == [5, 5]


async def test_manual_limit_cleared(
    hass: HomeAssistant, entry: MockConfigEntry, inverter: FakeInverter
) -> None:
    """The integration owns the limit: one set elsewhere is cleared while the price is fine."""
    inverter.enabled, inverter.percent = True, 50
    await poll(hass, entry)
    assert inverter.writes == [None]


async def test_setup_offline(
    hass: HomeAssistant, config_entry: MockConfigEntry, inverter: FakeInverter
) -> None:
    """Setup at night succeeds; the controls are there, the readings unavailable."""
    inverter.online = False
    hass.states.async_set(PRICE, "0.30")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "auto"
    assert hass.states.get(LIMIT).state == "unavailable"


async def test_restore(
    hass: HomeAssistant, config_entry: MockConfigEntry, inverter: FakeInverter
) -> None:
    """Mode and threshold survive a restart and apply at once."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (State(MODE, "off"), {}),
            (
                State(THRESHOLD, "0.5"),
                {
                    "native_value": 0.5,
                    "native_min_value": -1.0,
                    "native_max_value": 1.0,
                    "native_step": 0.001,
                    "native_unit_of_measurement": "€/kWh",
                },
            ),
        ],
    )
    hass.states.async_set(PRICE, "0.30")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "off"
    assert hass.states.get(THRESHOLD).state == "0.5"
    assert inverter.writes == []

    await hass.services.async_call(
        "select", "select_option", {"entity_id": MODE, "option": "auto"}, blocking=True
    )
    await hass.async_block_till_done()
    assert inverter.writes == [5]  # 0.30 < 0.5


async def test_remove_clears_limit(
    hass: HomeAssistant, entry: MockConfigEntry, inverter: FakeInverter
) -> None:
    """Removing the integration doesn't leave the inverter curtailed."""
    await set_price(hass, "-0.01")
    assert inverter.writes == [5]
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert inverter.writes == [5, None]
