from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    DOMAIN,
    CONF_AREA_CODE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_HIDS,
    CONF_APP_TYPE,
    CONF_GROUP_MULTI_ZONE_DEVICES,
    CONF_VALVE_DURATION_UNIT,
    CONF_TELEMETRY_CHOICE,
    CONF_TELEMETRY_COUNTRY,
    CONF_TELEMETRY_MODELS,
    APP_TYPE_HOMGAR,
    APP_TYPE_RAINPOINT,
    DEFAULT_VALVE_DURATION_UNIT,
    VALVE_DURATION_UNIT_MINUTES,
    VALVE_DURATION_UNIT_SECONDS,
)
from .country_codes import get_default_country_code
from .api import HomGarClient, HomGarApiError

_LOGGER = logging.getLogger(__name__)

# `section` groups fields into a collapsible sub-form in the options flow UI
# and was added in HA 2024.6. hacs.json declares a floor of 2024.5.0, so an
# unconditional import would break setup outright on that floor — the same
# class of problem as UnitOfRatio (see sensor_defs.py and issue #84). Import
# it where it exists and fall back to a flat schema (no section, no `└`
# fake-indentation either — see _build_options_schema) where it doesn't.
try:  # HA >= 2024.6
    from homeassistant.data_entry_flow import section
except ImportError:  # pragma: no cover - exercised on HA < 2024.6
    section = None

# Key the telemetry sub-toggles are nested under when `section` is in use.
# The frontend nests submitted values under this key; _flatten_telemetry_section
# below undoes that so stored options always end up flat, regardless of core
# version, so existing (flat) options entries keep working unchanged.
_TELEMETRY_SECTION_KEY = "telemetry_details"


def _normalize_email(email: str) -> str:
    """Normalize email for config-entry identity comparisons."""
    return email.strip().casefold()


def _normalize_area_code(area_code: str) -> str:
    """Normalize area code for config-entry identity comparisons."""
    return str(area_code).strip()


def _build_account_unique_id(area_code: str, email: str, app_type: str) -> str:
    """Build the unique ID for new config entries.

    Include app type and area code so the same email can be used across
    separate HomGar and RainPoint accounts without colliding.
    """
    return f"{DOMAIN}_{app_type}_{_normalize_area_code(area_code)}_{_normalize_email(email)}"


def _entry_matches_account(entry, area_code: str, email: str, app_type: str) -> bool:
    """Return True if a config entry represents the same account."""
    data = entry.data
    return (
        _normalize_email(data.get(CONF_EMAIL, "")) == _normalize_email(email)
        and _normalize_area_code(data.get(CONF_AREA_CODE, "")) == _normalize_area_code(area_code)
        and data.get(CONF_APP_TYPE, APP_TYPE_HOMGAR) == app_type
    )


class HomGarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HomGar/RainPoint Smart+ devices."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._reconfigure = False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return HomGarOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            area_code = user_input[CONF_AREA_CODE]
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            app_type = user_input[CONF_APP_TYPE]

            # Backward-compatible duplicate detection:
            # match existing entries by account fields so legacy entries that
            # used email-only unique IDs still block true duplicates.
            for existing_entry in self.hass.config_entries.async_entries(DOMAIN):
                if _entry_matches_account(existing_entry, area_code, email, app_type):
                    return self.async_abort(reason="already_configured")

            # New entries use a stronger unique ID that includes app type and
            # area code, allowing the same email across separate ecosystems.
            await self.async_set_unique_id(
                _build_account_unique_id(area_code, email, app_type)
            )
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            _LOGGER.debug("Creating client with app_type: %s", app_type)
            client = HomGarClient(area_code, email, password, session, app_type)

            try:
                await client.ensure_logged_in()
                homes = await client.list_homes()
                _LOGGER.debug("Found %d homes for app_type %s", len(homes), app_type)
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

        # Get default country code from Home Assistant configuration
        default_country_code = get_default_country_code(self.hass)
        
        data_schema = vol.Schema(
            {
                vol.Required(CONF_AREA_CODE, default=default_country_code): str,
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
        _LOGGER.debug("Available homes: %s", home_options)

        if user_input is not None:
            selected = user_input.get(CONF_HIDS)
            if not selected:
                errors["base"] = "select_at_least_one"
            else:
                hids = [int(h) for h in selected]
                _LOGGER.debug("Selected home IDs: %s", hids)

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

        # Multi-select checkboxes — one or more homes
        data_schema = vol.Schema(
            {
                vol.Required(CONF_HIDS): cv.multi_select(home_options)
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
        
        # Get default country code from Home Assistant configuration
        default_country_code = get_default_country_code(self.hass)
        
        # Pre-fill form with current values
        data_schema = vol.Schema(
            {
                vol.Required(CONF_AREA_CODE, default=current_data.get(CONF_AREA_CODE, default_country_code)): str,
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

            for existing_entry in self.hass.config_entries.async_entries(DOMAIN):
                if existing_entry.entry_id == entry.entry_id:
                    continue
                if _entry_matches_account(existing_entry, area_code, email, app_type):
                    return self.async_abort(reason="already_configured")

            # Test new credentials
            session = async_get_clientsession(self.hass)
            client = HomGarClient(area_code, email, password, session, app_type)

            try:
                await client.ensure_logged_in()
                homes = await client.list_homes()
                _LOGGER.debug("Found %d homes for reconfigure", len(homes))
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
                hids = [int(h) for h in selected]

                if user_input.get("clean_registry"):
                    _LOGGER.info("Reconfigure: removing all existing devices and entities for entry %s", current_entry.entry_id)
                    ent_reg = er.async_get(self.hass)
                    dev_reg = dr.async_get(self.hass)
                    entity_entries = er.async_entries_for_config_entry(ent_reg, current_entry.entry_id)
                    for entity_entry in entity_entries:
                        ent_reg.async_remove(entity_entry.entity_id)
                    device_entries = dr.async_entries_for_config_entry(dev_reg, current_entry.entry_id)
                    for device_entry in device_entries:
                        dev_reg.async_remove_device(device_entry.id)
                    _LOGGER.info("Reconfigure: removed %d entities and %d devices", len(entity_entries), len(device_entries))

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

        # Pre-select currently configured homes
        current_selected = {str(h) for h in current_hids}

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HIDS, default=current_selected): cv.multi_select(home_options),
                vol.Optional("clean_registry", default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="select_homes_reconfigure",
            data_schema=data_schema,
            errors=errors,
        )


def _flatten_telemetry_section(user_input: dict[str, Any]) -> dict[str, Any]:
    """Flatten the telemetry sub-toggles back out of their UI section.

    When `section` is available, the frontend nests CONF_TELEMETRY_COUNTRY
    and CONF_TELEMETRY_MODELS under `_TELEMETRY_SECTION_KEY` in the submitted
    data. Options must always be stored flat — so existing entries (written
    before `section` existed, or by a core below 2024.6 that never had it)
    keep working unchanged. A no-op when the section key isn't present.
    """
    data = dict(user_input)
    nested = data.pop(_TELEMETRY_SECTION_KEY, None)
    if isinstance(nested, dict):
        data.update(nested)
    return data


def _build_options_schema(
    defaults: dict[str, Any],
    section_impl: Any = section,
) -> vol.Schema:
    """Build the options-flow schema.

    Split out from async_step_init so it can be built and inspected without
    a running HomeAssistant instance. `section_impl` defaults to the guarded
    module-level import (so production always reflects what this core
    actually supports); tests pass it explicitly to exercise both the
    HA >= 2024.6 and HA < 2024.6 paths deterministically, independent of
    which core the test container happens to run.
    """
    schema_dict: dict[Any, Any] = {
        vol.Optional(
            CONF_GROUP_MULTI_ZONE_DEVICES,
            default=defaults.get(CONF_GROUP_MULTI_ZONE_DEVICES, False),
        ): bool,
        vol.Optional(
            CONF_VALVE_DURATION_UNIT,
            default=defaults.get(CONF_VALVE_DURATION_UNIT, DEFAULT_VALVE_DURATION_UNIT),
        ): vol.In({
            VALVE_DURATION_UNIT_MINUTES: "Minutes",
            VALVE_DURATION_UNIT_SECONDS: "Seconds",
        }),
        vol.Optional(
            CONF_TELEMETRY_CHOICE,
            default=defaults.get(CONF_TELEMETRY_CHOICE, False),
        ): bool,
    }

    sub_toggles = {
        vol.Optional(
            CONF_TELEMETRY_COUNTRY,
            default=defaults.get(CONF_TELEMETRY_COUNTRY, False),
        ): bool,
        vol.Optional(
            CONF_TELEMETRY_MODELS,
            default=defaults.get(CONF_TELEMETRY_MODELS, False),
        ): bool,
    }

    if section_impl is not None:
        # Collapsible sub-section grouping the two toggles that are inert
        # without the master switch above — see translations/en.json
        # options.step.init.sections for the section's own label/description.
        schema_dict[vol.Optional(_TELEMETRY_SECTION_KEY)] = section_impl(
            vol.Schema(sub_toggles), {"collapsed": False}
        )
    else:
        schema_dict.update(sub_toggles)

    return vol.Schema(schema_dict)


class HomGarOptionsFlow(config_entries.OptionsFlow):
    """Handle HomGar options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            from homeassistant.components import persistent_notification

            from .telemetry import TELEMETRY_NOTIFICATION_ID

            persistent_notification.async_dismiss(
                self.hass, TELEMETRY_NOTIFICATION_ID
            )

            return self.async_create_entry(
                title="", data=_flatten_telemetry_section(user_input)
            )

        data_schema = _build_options_schema(dict(self._config_entry.options))

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
        )
