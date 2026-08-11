"""
telemetry.py — opt-in, off-by-default anonymous telemetry.

Answers one question for the maintainer: how many people run this integration
and roughly where. Nothing is sent unless the user explicitly switches it on.

Design notes that matter:
  * The client NEVER sends location. It sends a `share_country` flag; the
    Cloudflare worker derives the country at the edge and stores it only as a
    monthly aggregate that cannot be joined back to an install.
  * `models` is omitted from the payload entirely when not opted in, rather
    than sent as an empty list — the wire format should not imply we asked.
  * `anon_id` is a random UUID4 with no relationship to the account, email or
    any device identifier.
  * No User-Agent override. The HomGar cloud blocks HA's default UA (issue
    #76) but the telemetry worker does not — verified by spike.

See docs/superpowers/specs/2026-08-11-optin-telemetry-design.md
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

_LOGGER = logging.getLogger(__name__)

TELEMETRY_URL = "https://homgar-telemetry-worker.funkypeople.workers.dev/ping"
PING_INTERVAL_HOURS = 24
PING_TIMEOUT_SECONDS = 10


def is_telemetry_enabled(options: dict) -> bool:
    """True only when the master switch is explicitly on.

    The sub-toggles are meaningless on their own — enabling "include my
    country" without the master switch must never cause a request.
    """
    from .const import CONF_TELEMETRY_CHOICE

    return options.get(CONF_TELEMETRY_CHOICE) is True


def build_payload(
    anon_id: str,
    integration_version: str,
    hass_version: str,
    share_country: bool,
    share_models: bool,
    models: list[str] | None,
) -> dict[str, Any]:
    """Build the complete wire payload. This is the ONLY place a payload is
    constructed, so it is the single place to audit what leaves a user's
    machine."""
    payload: dict[str, Any] = {
        "anon_id": anon_id,
        "integration_version": integration_version,
        "hass_version": hass_version,
        "share_country": bool(share_country),
        "share_models": bool(share_models),
    }
    if share_models:
        payload["models"] = list(models or [])
    return payload


def models_from_coordinator_data(data: dict | None) -> list[str]:
    """Extract the distinct device model names from a coordinator payload.

    Model names only — never serial numbers, addresses, names or home IDs.
    """
    if not data:
        return []
    found: set[str] = set()
    for hub in data.get("hubs") or []:
        model = hub.get("model")
        if model and model != "Unknown":
            found.add(str(model))
        for sub in hub.get("subDevices") or []:
            sub_model = sub.get("model")
            if sub_model:
                found.add(str(sub_model))
    return sorted(found)


def should_ping(
    last_ping_at: Any, now: datetime, interval_hours: int = PING_INTERVAL_HOURS
) -> bool:
    """Whether enough time has passed since the last successful ping.

    Tolerates a missing, malformed or future timestamp: a corrupt value must
    never wedge telemetry permanently on or permanently off. A future value
    (clock skew, restored backup) blocks until it passes rather than pinging
    every cycle.
    """
    if last_ping_at is None:
        return True
    if isinstance(last_ping_at, str):
        try:
            last_ping_at = datetime.fromisoformat(last_ping_at)
        except (TypeError, ValueError):
            return True
    if not isinstance(last_ping_at, datetime):
        return True
    if last_ping_at.tzinfo is None:
        last_ping_at = last_ping_at.replace(tzinfo=timezone.utc)
    if last_ping_at > now:
        return False
    return now - last_ping_at >= timedelta(hours=interval_hours)
