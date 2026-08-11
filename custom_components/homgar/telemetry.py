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


async def async_maybe_ping(hass, entry, coordinator_data, session) -> bool:
    """Send one telemetry ping if enabled and due. Returns True if sent.

    This function must NEVER raise. It runs inside the coordinator's poll
    cycle, and a user's irrigation must not depend on a stats endpoint being
    reachable. Every failure path is swallowed at debug level.
    """
    from uuid import uuid4

    from .const import (
        CONF_ANON_ID,
        CONF_LAST_PING_AT,
        CONF_TELEMETRY_COUNTRY,
        CONF_TELEMETRY_MODELS,
    )

    try:
        options = dict(getattr(entry, "options", {}) or {})
        if not is_telemetry_enabled(options):
            return False

        data = dict(getattr(entry, "data", {}) or {})
        now = datetime.now(timezone.utc)
        if not should_ping(data.get(CONF_LAST_PING_AT), now):
            return False

        anon_id = data.get(CONF_ANON_ID)
        if not anon_id:
            anon_id = str(uuid4())
            hass.config_entries.async_update_entry(
                entry, data={**data, CONF_ANON_ID: anon_id}
            )
            data = {**data, CONF_ANON_ID: anon_id}

        share_country = options.get(CONF_TELEMETRY_COUNTRY) is True
        share_models = options.get(CONF_TELEMETRY_MODELS) is True

        payload = build_payload(
            anon_id,
            await _async_integration_version(hass),
            _hass_version(),
            share_country,
            share_models,
            models_from_coordinator_data(coordinator_data) if share_models else None,
        )

        import aiohttp

        async with session.post(
            TELEMETRY_URL,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=PING_TIMEOUT_SECONDS),
        ) as resp:
            if resp.status != 204:
                _LOGGER.debug("Telemetry ping returned HTTP %s", resp.status)
                return False

        # Only stamp on success, so a failed ping retries on the next cycle
        # rather than being silently skipped for a day.
        hass.config_entries.async_update_entry(
            entry, data={**data, CONF_LAST_PING_AT: now.isoformat()}
        )
        _LOGGER.debug("Telemetry ping sent")
        return True
    except Exception as err:  # noqa: BLE001 - telemetry must never break setup
        _LOGGER.debug("Telemetry ping failed (ignored): %s", err)
        return False


def _async_create_notification(hass, message, title=None, notification_id=None):
    """Indirection so tests can capture the notification without a real hass."""
    from homeassistant.components import persistent_notification

    persistent_notification.async_create(
        hass, message, title=title, notification_id=notification_id
    )


TELEMETRY_NOTIFICATION_ID = "homgar_telemetry_optin"

_OPTIN_MESSAGE = (
    "This integration can optionally report **anonymous** usage data, so I can "
    "see how many people use it and roughly where in the world they are. It is "
    "**off by default** and entirely your choice.\n\n"
    "If you switch it on you choose separately whether to include your country "
    "and your device models. The base data is an anonymous random ID plus the "
    "Home Assistant and integration version numbers.\n\n"
    "No account details, no location beyond an optional country, and your IP is "
    "never stored.\n\n"
    "[Open settings](/config/integrations/integration/homgar) — or ignore this; "
    "it will not ask again."
)


async def async_prompt_for_telemetry_once(hass, entry) -> bool:
    """Show the opt-in prompt if the user has never answered. Returns True if
    shown.

    Fires only when no choice exists. Recording any answer — including "no" —
    stops it permanently.
    """
    from .const import CONF_TELEMETRY_CHOICE

    try:
        options = dict(getattr(entry, "options", {}) or {})
        if CONF_TELEMETRY_CHOICE in options:
            return False
        _async_create_notification(
            hass,
            _OPTIN_MESSAGE,
            title="HomGar/RainPoint: optional anonymous usage data",
            notification_id=TELEMETRY_NOTIFICATION_ID,
        )
        return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Telemetry opt-in prompt failed (ignored): %s", err)
        return False


def _hass_version() -> str:
    try:
        from homeassistant.const import __version__

        return str(__version__)
    except Exception:  # noqa: BLE001
        return "unknown"


async def _async_integration_version(hass) -> str:
    """Read the version from manifest.json rather than duplicating it."""
    try:
        from homeassistant.loader import async_get_integration

        from .const import DOMAIN

        integration = await async_get_integration(hass, DOMAIN)
        return str(integration.version)
    except Exception:  # noqa: BLE001
        return "unknown"
