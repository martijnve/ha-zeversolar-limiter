"""Config flow: host (checked via home.cgi, unique by serial), price entity; reconfigure the host."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .api import Status, ZeversolarClient, ZeversolarError
from .const import CONF_PRICE_ENTITY, DEFAULT_PRICE_ENTITY, DOMAIN
from .entity import CONF_HARDWARE, CONF_SOFTWARE

PRICE_SELECTOR = EntitySelector(EntitySelectorConfig(domain="sensor"))


class ZeversolarLimiterConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per inverter."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the host and the price entity."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if (status := await self._probe(host)) is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(status.serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=f"Zeversolar {status.serial}",
                    data=_data(host, status),
                    options={CONF_PRICE_ENTITY: user_input[CONF_PRICE_ENTITY]},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(
                        CONF_PRICE_ENTITY, default=DEFAULT_PRICE_ENTITY
                    ): PRICE_SELECTOR,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """New host for the same inverter."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if (status := await self._probe(host)) is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(status.serial)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data=_data(host, status)
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        """Price entity."""
        return OptionsFlow()

    async def _probe(self, host: str) -> Status | None:
        try:
            return await ZeversolarClient(
                async_get_clientsession(self.hass), host
            ).status()
        except ZeversolarError:
            return None


class OptionsFlow(OptionsFlowWithReload):
    """Change the price entity (reloads the entry)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the price entity."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_PRICE_ENTITY, DEFAULT_PRICE_ENTITY)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_PRICE_ENTITY, default=current): PRICE_SELECTOR}
            ),
        )


def _data(host: str, status: Status) -> dict[str, str]:
    return {
        CONF_HOST: host,
        CONF_HARDWARE: status.hardware,
        CONF_SOFTWARE: status.software,
    }
