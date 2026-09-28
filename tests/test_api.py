"""The HTTP client against recorded inverter responses."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.zeversolar_limiter.api import (
    ZeversolarClient,
    ZeversolarError,
    parse_limit,
    parse_status,
)

from .conftest import SERIAL, fixture

URL = "http://inverter.local"


@pytest.fixture
async def client(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> ZeversolarClient:
    """Client for inverter.local, on the mocked session."""
    return ZeversolarClient(async_get_clientsession(hass), "inverter.local")


def test_parse_status() -> None:
    """M11 home.cgi: time and date on one line, cloud status 6 (no cloud), energy 1.7 = 1.07 kWh."""
    status = parse_status(fixture("home.txt"))
    assert status.serial == SERIAL
    assert status.hardware == "M11"
    assert status.software == "18625-797R+17829-719R"
    assert status.power == 846
    assert status.energy_today == 1.07
    assert status.ok


def test_parse_status_extra_field() -> None:
    """Firmware with a field between serial and power."""
    text = fixture("home.txt").replace(f"{SERIAL}\n", f"{SERIAL}\nX\n")
    assert parse_status(text).power == 846


@pytest.mark.parametrize(
    "text", ["", "1\n1\n", fixture("home.txt").replace("\n1\nZS", "\n0\nZS")]
)
def test_parse_status_invalid(text: str) -> None:
    """Too short, or no inverter."""
    with pytest.raises(ZeversolarError):
        parse_status(text)


def test_parse_limit() -> None:
    """adv.cgi, off and at 5 %."""
    off = parse_limit(fixture("adv_off.txt"))
    assert not off.enabled
    assert off.percent == 100
    assert off.fields == {
        "drm_sp": "16.67",
        "ac_sys": "0",
        "ac_value1": "100",
        "ac_value2": "0",
        "ac_value3": "60",
        "ac_mode": "1",
        "em_ml": "0",
    }
    on = parse_limit(fixture("adv_on_5.txt"))
    assert on.enabled
    assert on.percent == 5


async def test_set_limit_posts_form_and_reads_back(
    client: ZeversolarClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """enlim=on, percentage mode, the other fields as the inverter had them."""
    aioclient_mock.get(f"{URL}/adv.cgi", text=fixture("adv_on_5.txt"))
    aioclient_mock.post(f"{URL}/pwrlim.cgi", text="")
    limit = await client.set_limit(5)
    assert limit.percent == 5
    posts = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][2] == {
        "enlim": "on",
        "drm_sp": "16.67",
        "ac_sys": "0",
        "ac_value1": "5",
        "ac_value2": "0",
        "ac_value3": "60",
        "ac_mode": "1",
        "em_ml": "0",
    }


async def test_clear_limit_leaves_enlim_out(
    client: ZeversolarClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """As the web UI with the box unchecked."""
    aioclient_mock.get(f"{URL}/adv.cgi", text=fixture("adv_off.txt"))
    aioclient_mock.post(f"{URL}/pwrlim.cgi", text="")
    limit = await client.clear_limit()
    assert not limit.enabled
    post = next(call for call in aioclient_mock.mock_calls if call[0] == "POST")
    assert "enlim" not in post[2]
    assert post[2]["ac_value1"] == "100"


async def test_write_not_applied(
    client: ZeversolarClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """The read-back decides: still off after a limit write is an error."""
    aioclient_mock.get(f"{URL}/adv.cgi", text=fixture("adv_off.txt"))
    aioclient_mock.post(f"{URL}/pwrlim.cgi", text="")
    with pytest.raises(ZeversolarError, match="kept 100"):
        await client.set_limit(5)


async def test_disconnect_after_post_is_not_an_error(
    client: ZeversolarClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Firmware that closes the connection instead of answering."""
    aioclient_mock.get(f"{URL}/adv.cgi", text=fixture("adv_on_5.txt"))
    aioclient_mock.post(f"{URL}/pwrlim.cgi", exc=aiohttp.ServerDisconnectedError())
    assert (await client.set_limit(5)).percent == 5


async def test_read_retries_once(
    client: ZeversolarClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A timeout is retried once, then reported."""
    aioclient_mock.get(f"{URL}/home.cgi", exc=TimeoutError())
    with pytest.raises(ZeversolarError):
        await client.status()
    assert aioclient_mock.call_count == 2
