"""Fixtures: a fake inverter in place of the HTTP client, and a set-up entry."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeversolar_limiter.api import Limit, Status, ZeversolarError
from custom_components.zeversolar_limiter.const import CONF_PRICE_ENTITY, DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
SERIAL = "ZS300000000B0001"
PRICE = "sensor.price"


def fixture(name: str) -> str:
    """Contents of tests/fixtures/<name>."""
    return (FIXTURES / name).read_text()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


class FakeInverter:
    """Keeps a power limit like the real one; `online = False` makes every call fail."""

    def __init__(self) -> None:
        """Online, producing, no limit."""
        self.online = True
        self.serial = SERIAL
        self.power = 846
        self.enabled = False
        self.percent = 100
        self.writes: list[int | None] = []  # percent, or None for a clear

    async def status(self) -> Status:
        """Fake home.cgi."""
        self._check()
        return Status(
            serial=self.serial,
            hardware="M11",
            software="1.0",
            power=self.power,
            energy_today=1.07,
            ok=True,
        )

    async def limit(self) -> Limit:
        """Fake adv.cgi."""
        self._check()
        fields = {
            "drm_sp": "16.67",
            "ac_sys": "0",
            "ac_value1": str(self.percent),
            "ac_value2": "0",
            "ac_value3": "60",
            "ac_mode": "1",
            "em_ml": "0",
        }
        return Limit(enabled=self.enabled, fields=fields)

    async def set_limit(self, percent: int) -> Limit:
        """Fake limit."""
        self._check()
        self.writes.append(percent)
        self.enabled, self.percent = True, percent
        return await self.limit()

    async def clear_limit(self) -> Limit:
        """Fake clear."""
        self._check()
        self.writes.append(None)
        self.enabled, self.percent = False, 100
        return await self.limit()

    def _check(self) -> None:
        if not self.online:
            raise ZeversolarError("offline")


@pytest.fixture
def inverter() -> Iterator[FakeInverter]:
    """The fake, used by setup and the config flow."""
    fake = FakeInverter()
    with (
        patch(
            "custom_components.zeversolar_limiter.ZeversolarClient",
            lambda session, host: fake,
        ),
        patch(
            "custom_components.zeversolar_limiter.config_flow.ZeversolarClient",
            lambda session, host: fake,
        ),
    ):
        yield fake


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """An entry for the fake inverter, following sensor.price."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL,
        title=f"Zeversolar {SERIAL}",
        data={CONF_HOST: "inverter.local", "hardware": "M11", "software": "1.0"},
        options={CONF_PRICE_ENTITY: PRICE},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def entry(
    hass: HomeAssistant, config_entry: MockConfigEntry, inverter: FakeInverter
) -> MockConfigEntry:
    """Set up with a price of 0.30."""
    hass.states.async_set(PRICE, "0.30")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
