"""Diagnostics for the HomGar/RainPoint integration.

Device-support issues used to be worked from hand-pasted logs, which meant the
one line that mattered was routinely missing — issue #97's report began directly
after the ``Found N devices for HID`` line that would have identified the
device. This exposes Home Assistant's standard "Download diagnostics" button
instead, so a reporter can hand over the full picture in one attachment.

What is captured is chosen for diagnosing *unknown hardware*: the raw cloud rows
and status envelopes exactly as received (an explicit ``"data": null`` must
arrive as null, not normalised away), the catalogue version the install is
running, and any model our catalogue has never seen.

Everything is redacted through ``TO_REDACT`` before it leaves, because these
files get pasted into public issues. ``mid`` is deliberately retained: it is a
device identifier rather than a credential, and keeping it lets a maintainer
follow one device through a long thread.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_APP_TYPE, DOMAIN
from .decoder import _MODELS_FILE, _load_models, get_model_info

_LOGGER = logging.getLogger(__name__)

# Account identifiers and device credentials. Anything here can identify the
# reporter or be replayed against their account, so none of it may survive into
# a file destined for a public issue thread.
TO_REDACT = {
    "email",
    "phoneOrEmail",
    "password",
    "token",
    "refreshToken",
    "deviceId",
    "iotId",
    "productKey",
    "deviceName",
    "mac",
    "hid",
    "did",
    "homeName",
    "name",
    # The config entry title is assembled as "HomGar/RainPoint (<email>)", so the
    # account address rides along inside free text. Key-based redaction cannot
    # see a substring, so the whole field goes — caught by auditing a real
    # download rather than by reading the key list.
    "title",
}


def _redact(data: Any) -> Any:
    """Redact credentials and account identifiers, recursively."""
    return async_redact_data(data, TO_REDACT)


def _catalogue_summary() -> dict:
    """Describe the shipped product catalogue.

    The catalogue is a static snapshot, so a device newer than it decodes as
    "unknown model" for reasons that have nothing to do with the user's setup.
    Reporting its version up front makes that immediately visible.
    """
    models = _load_models()
    version = None
    try:
        import json

        with open(_MODELS_FILE, encoding="utf-8") as handle:
            version = json.load(handle).get("data", {}).get("version")
    except Exception as err:  # noqa: BLE001 — diagnostics must never fail hard
        _LOGGER.debug("Could not read catalogue version: %s", err)
    return {
        "version": version,
        "model_count": len(models),
        "source": str(_MODELS_FILE),
    }


def _unknown_models(hubs: list[dict]) -> list[str]:
    """Return models present on the account but absent from our catalogue.

    These are the devices that cannot decode, so naming them is usually the
    whole answer to a device-support report.
    """
    seen: set[str] = set()
    for hub in hubs or []:
        candidates = [hub.get("model")]
        candidates.extend(sub.get("model") for sub in (hub.get("subDevices") or []))
        for model in candidates:
            if model and get_model_info(model) is None:
                seen.add(model)
    return sorted(seen)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return redacted diagnostics for one config entry."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}) or {}
    coordinator = entry_data.get("coordinator")
    client = entry_data.get("client")
    data = (coordinator.data if coordinator else None) or {}
    hubs = data.get("hubs") or []

    diagnostics: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "app_type": entry.data.get(CONF_APP_TYPE),
            "version": entry.version,
        },
        "catalogue": _catalogue_summary(),
        "unknown_models": _unknown_models(hubs),
        "hubs": hubs,
        "status": data.get("status") or {},
        "sensors": data.get("sensors") or {},
        "mqtt_diagnostics": data.get("mqtt_diagnostics") or {},
    }

    # Raw, unnormalised envelopes. The client's own null-guard makes a missing
    # payload indistinguishable from an empty one by the time it reaches the
    # coordinator, so fetch these directly — a `"data": null` is the signature
    # of a device with no cloud status at all (issue #97) and must be visible.
    raw: dict[str, Any] = {}
    if client is not None:
        for hub in hubs:
            mid = hub.get("mid")
            if mid is None:
                continue
            try:
                raw[str(mid)] = await client.raw_device_status(int(mid))
            except Exception as err:  # noqa: BLE001 — never fail the download
                raw[str(mid)] = {"error": f"{type(err).__name__}: {err}"}
    diagnostics["raw_device_status"] = raw

    return _redact(diagnostics)
