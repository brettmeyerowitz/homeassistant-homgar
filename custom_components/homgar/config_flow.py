from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_AREA_CODE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_HIDS,
)
from .homgar_api import HomGarClient, HomGarApiError

_LOGGER = logging.getLogger(__name__)


class HomGarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HomGar."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            area_code = user_input[CONF_AREA_CODE]
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            # Single account per HA instance
            await self.async_set_unique_id(f"{DOMAIN}_{email}")
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = HomGarClient(area_code, email, password, session)

            try:
                await client.ensure_logged_in()
                homes = await client.list_homes()
            except HomGarApiError:
                _LOGGER.exception("Error logging in to HomGar")
                errors["base"] = "auth_failed"
            except aiohttp.ClientError:
                _LOGGER.exception("Network error talking to HomGar")
                errors["base"] = "cannot_connect"
            else:
                if not homes:
                    errors["base"] = "no_homes"
                else:
                    # Store temp values for the next step
                    self._area_code = area_code
                    self._email = email
                    self._password = password
                    self._homes = homes
                    self._client = client
                    return await self.async_step_select_homes()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_AREA_CODE, default="27"): str,
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_select_homes(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        home_options = {str(h["hid"]): h["homeName"] for h in self._homes}

        if user_input is not None:
            selected = user_input.get(CONF_HIDS)
            if not selected:
                errors["base"] = "select_at_least_one"
            else:
                # single home for now
                hids = [int(selected)]

                token_data = self._client.export_tokens()

                data = {
                    CONF_AREA_CODE: self._area_code,
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_HIDS: hids,
                    **token_data,
                }

                return self.async_create_entry(
                    title=f"HomGar ({self._email})",
                    data=data,
                )

        # single-select dropdown – keys are HIDs, labels come from options dict
        data_schema = vol.Schema(
            {
                vol.Required(CONF_HIDS): vol.In(home_options)
            }
        )

        return self.async_show_form(
            step_id="select_homes",
            data_schema=data_schema,
            errors=errors,
        )