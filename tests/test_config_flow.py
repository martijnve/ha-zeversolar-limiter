"""Config, reconfigure and options flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeversolar_limiter.const import CONF_PRICE_ENTITY, DOMAIN

from .conftest import SERIAL, FakeInverter


async def test_user_flow(hass: HomeAssistant, inverter: FakeInverter) -> None:
    """Host checked via home.cgi; the serial is the unique id; a second entry is refused."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    inverter.online = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "inverter.local", CONF_PRICE_ENTITY: "sensor.price"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    inverter.online = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: " inverter.local ", CONF_PRICE_ENTITY: "sensor.price"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Zeversolar {SERIAL}"
    assert result["data"] == {
        CONF_HOST: "inverter.local",
        "hardware": "M11",
        "software": "1.0",
    }
    assert result["options"] == {CONF_PRICE_ENTITY: "sensor.price"}
    assert result["result"].unique_id == SERIAL

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.2", CONF_PRICE_ENTITY: "sensor.price"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert hass.config_entries.async_entries(DOMAIN)[0].data[CONF_HOST] == "10.0.0.2"


async def test_reconfigure(
    hass: HomeAssistant, entry: MockConfigEntry, inverter: FakeInverter
) -> None:
    """New host for the same inverter; another inverter is refused."""
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.3"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "10.0.0.3"

    inverter.serial = "ZS999"
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.4"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert entry.data[CONF_HOST] == "10.0.0.3"


async def test_options(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Another price sensor; the entry reloads onto it."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PRICE_ENTITY: "sensor.other_price"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.curtailer.price_entity == "sensor.other_price"
