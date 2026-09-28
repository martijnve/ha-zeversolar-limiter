"""Local client for a Zeversolar inverter's Wi-Fi module (MXCHIP web UI, M11 firmware).

- `home.cgi`: one value per line, whitespace-separated: wifi flag, ?, registry id, registry key,
  hardware, software, time, date, cloud status, number of inverters, then per inverter serial, AC
  power (W), energy today (kWh), status, meter status.
- `adv.cgi`: one value per line; index 8 is the power-limit checkbox (`enlim`), 9-15 the form
  fields below.
- `pwrlim.cgi`: POST of the advanced page's power-limit form. The web UI leaves `enlim` out when the
  box is unchecked, so clearing the limit does the same.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=10)
READ_ATTEMPTS = 2

# adv.cgi line index of each pwrlim.cgi form field.
LIMIT_FIELDS = {
    "drm_sp": 9,
    "ac_sys": 10,
    "ac_value1": 11,
    "ac_value2": 12,
    "ac_value3": 13,
    "ac_mode": 14,
    "em_ml": 15,
}
ENLIM_LINE = 8
PERCENTAGE_MODE = "1"


class ZeversolarError(Exception):
    """The inverter can't be reached or answered something unexpected."""


@dataclass(frozen=True)
class Status:
    """What home.cgi reports (first inverter only)."""

    serial: str
    hardware: str
    software: str
    power: int
    energy_today: float
    ok: bool


@dataclass(frozen=True)
class Limit:
    """The power-limit form as adv.cgi reports it."""

    enabled: bool
    fields: dict[str, str]

    @property
    def percent(self) -> int:
        """Output limit in %: 100 when the limit is off or not in percentage mode."""
        if not self.enabled or self.fields["ac_mode"] != PERCENTAGE_MODE:
            return 100
        return int(float(self.fields["ac_value1"]))


def parse_status(text: str) -> Status:
    """Parse home.cgi."""
    parts = text.split()
    try:
        if int(parts[9]) < 1:
            raise ZeversolarError("home.cgi reports no inverter")
        # Some firmware puts an extra field between serial and power (zeversolar 0.4.0).
        power = 12 if not parts[11].isdigit() else 11
        return Status(
            serial=parts[10],
            hardware=parts[4],
            software=parts[5],
            power=int(parts[power]),
            energy_today=_energy(parts[power + 1]),
            ok=parts[power + 2].upper() == "OK",
        )
    except (IndexError, ValueError) as err:
        raise ZeversolarError(f"unexpected home.cgi response: {text!r}") from err


def _energy(value: str) -> float:
    """kWh; the firmware drops the leading zero of the hundredths (1.7 means 1.07)."""
    whole, _, decimals = value.partition(".")
    if len(decimals) == 1:
        decimals = f"0{decimals}"
    return float(f"{whole}.{decimals or 0}")


def parse_limit(text: str) -> Limit:
    """Parse adv.cgi."""
    lines = [line.strip() for line in text.splitlines()]
    try:
        return Limit(
            enabled=lines[ENLIM_LINE] != "0",
            fields={name: lines[index] for name, index in LIMIT_FIELDS.items()},
        )
    except IndexError as err:
        raise ZeversolarError(f"unexpected adv.cgi response: {text!r}") from err


class ZeversolarClient:
    """Reads status and power limit, and sets or clears the limit."""

    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        """Talk to http://<host>/."""
        self.host = host
        self._session = session
        self._write_lock = asyncio.Lock()

    async def status(self) -> Status:
        """Current output, energy today and device info."""
        return parse_status(await self._get("home.cgi"))

    async def limit(self) -> Limit:
        """Current power-limit settings."""
        return parse_limit(await self._get("adv.cgi"))

    async def set_limit(self, percent: int) -> Limit:
        """Limit output to `percent` of the rated power; returns the limit read back."""
        async with self._write_lock:
            current = await self.limit()
            fields = current.fields | {
                "ac_mode": PERCENTAGE_MODE,
                "ac_value1": str(percent),
            }
            await self._post_limit({"enlim": "on"} | fields)
            return await self._verify(replace(current, enabled=True, fields=fields))

    async def clear_limit(self) -> Limit:
        """Full output: the limit box unchecked, other settings kept; returns the limit read back."""
        async with self._write_lock:
            current = await self.limit()
            fields = current.fields | {"ac_mode": PERCENTAGE_MODE, "ac_value1": "100"}
            await self._post_limit(fields)
            return await self._verify(replace(current, enabled=False, fields=fields))

    async def _verify(self, expected: Limit) -> Limit:
        actual = await self.limit()
        if actual.enabled != expected.enabled or actual.percent != expected.percent:
            raise ZeversolarError(
                f"inverter kept {actual.percent} % (enabled={actual.enabled}) after the write"
            )
        return actual

    async def _get(self, path: str) -> str:
        for attempt in range(READ_ATTEMPTS):
            try:
                async with self._session.get(
                    self._url(path), timeout=TIMEOUT
                ) as response:
                    response.raise_for_status()
                    return await response.text()
            except (TimeoutError, aiohttp.ClientError) as err:
                if attempt + 1 == READ_ATTEMPTS:
                    raise ZeversolarError(f"{path}: {err!r}") from err
        raise AssertionError("unreachable")

    async def _post_limit(self, data: dict[str, str]) -> None:
        try:
            async with self._session.post(
                self._url("pwrlim.cgi"), data=data, timeout=TIMEOUT
            ) as response:
                response.raise_for_status()
        except aiohttp.ServerDisconnectedError:
            # Some firmware closes the connection after applying the form without answering;
            # the read-back decides whether it worked.
            pass
        except (TimeoutError, aiohttp.ClientError) as err:
            raise ZeversolarError(f"pwrlim.cgi: {err!r}") from err

    def _url(self, path: str) -> str:
        return f"http://{self.host}/{path}"
