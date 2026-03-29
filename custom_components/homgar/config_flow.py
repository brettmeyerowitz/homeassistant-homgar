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
    CONF_APP_TYPE,
    APP_TYPE_HOMGAR,
    APP_TYPE_RAINPOINT,
)
from .homgar_api import HomGarClient, HomGarApiError

_LOGGER = logging.getLogger(__name__)


class HomGarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HomGar/RainPoint Smart+ devices."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._reconfigure = False

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            area_code = user_input[CONF_AREA_CODE]
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            app_type = user_input[CONF_APP_TYPE]

            # Single account per HA instance
            await self.async_set_unique_id(f"{DOMAIN}_{email}")
            if self._reconfigure:
                self._abort_if_unique_id_mismatch()
            else:
                self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            _LOGGER.info("Creating client with app_type: %s", app_type)
            client = HomGarClient(area_code, email, password, session, app_type)

            try:
                await client.ensure_logged_in()
                homes = await client.list_homes()
                _LOGGER.info("Found %d homes for app_type %s", len(homes), app_type)
                _LOGGER.debug("Homes data: %s", homes)
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
                    self._app_type = app_type
                    self._homes = homes
                    self._client = client
                    return await self.async_step_select_homes()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_AREA_CODE, default="27"): str,
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_APP_TYPE, default=APP_TYPE_HOMGAR): vol.In({
                    APP_TYPE_HOMGAR: "HomGar",  # Note: HA vol.In() doesn't support translation strings for options
                    APP_TYPE_RAINPOINT: "RainPoint",  # Field label is translated via strings.json
                }),
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
        _LOGGER.info("Available homes: %s", home_options)

        if user_input is not None:
            selected_hids = user_input["hids"]
            _LOGGER.info("Selected home IDs: %s", selected_hids)

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
                    CONF_APP_TYPE: self._app_type,
                    CONF_HIDS: hids,
                    **token_data,
                }

                if self._reconfigure:
                    return self.async_update_reload_and_abort(
                        self._get_reconfigure_entry(),
                        data=data,
                        title=f"HomGar/RainPoint ({self._email})",
                    )
                else:
                    return self.async_create_entry(
                        title=f"HomGar/RainPoint ({self._email})",
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

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle reconfiguration of the integration."""
        self._reconfigure = True
        
        # Get current entry data
        entry = self._get_reconfigure_entry()
        current_data = entry.data
        
        # Pre-fill form with current values
        data_schema = vol.Schema(
            {
                vol.Required(CONF_AREA_CODE, default=current_data.get(CONF_AREA_CODE, "27")): str,
                vol.Required(CONF_EMAIL, default=current_data.get(CONF_EMAIL, "")): str,
                vol.Required(CONF_PASSWORD, default=current_data.get(CONF_PASSWORD, "")): str,
                vol.Required(CONF_APP_TYPE, default=current_data.get(CONF_APP_TYPE, APP_TYPE_HOMGAR)): vol.In({
                    APP_TYPE_HOMGAR: "HomGar",
                    APP_TYPE_RAINPOINT: "RainPoint",
                }),
            }
        )
        
        if user_input is not None:
            area_code = user_input[CONF_AREA_CODE]
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            app_type = user_input[CONF_APP_TYPE]

            # Test new credentials
            session = async_get_clientsession(self.hass)
            client = HomGarClient(area_code, email, password, session, app_type)

            try:
                await client.ensure_logged_in()
                homes = await client.list_homes()
                _LOGGER.info("Found %d homes for reconfigure", len(homes))
            except HomGarApiError:
                _LOGGER.exception("Error logging in to HomGar during reconfigure")
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=data_schema,
                    errors={"base": "auth_failed"},
                )
            except aiohttp.ClientError:
                _LOGGER.exception("Network error during reconfigure")
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=data_schema,
                    errors={"base": "cannot_connect"},
                )
            else:
                if not homes:
                    return self.async_show_form(
                        step_id="reconfigure",
                        data_schema=data_schema,
                        errors={"base": "no_homes"},
                    )
                else:
                    # Store temp values for the next step
                    self._area_code = area_code
                    self._email = email
                    self._password = password
                    self._app_type = app_type
                    self._homes = homes
                    self._client = client
                    return await self.async_step_select_homes_reconfigure()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
        )

    async def async_step_select_homes_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle home selection during reconfiguration."""
        errors: dict[str, str] = {}
        
        home_options = {str(h["hid"]): h["homeName"] for h in self._homes}
        current_entry = self._get_reconfigure_entry()
        current_hids = current_entry.data.get(CONF_HIDS, [])
        
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
                    CONF_APP_TYPE: self._app_type,
                    CONF_HIDS: hids,
                    **token_data,
                }

                return self.async_update_reload_and_abort(
                    current_entry,
                    data=data,
                    title=f"HomGar/RainPoint ({self._email})",
                )

        # Pre-select current home
        current_hid = str(current_hids[0]) if current_hids else None
        
        data_schema = vol.Schema(
            {
                vol.Required(CONF_HIDS, default=current_hid): vol.In(home_options)
            }
        )

        return self.async_show_form(
            step_id="select_homes_reconfigure",
            data_schema=data_schema,
            errors=errors,
        )