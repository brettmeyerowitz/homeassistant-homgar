import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.components.persistent_notification import async_create
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    APP_TYPE_HOMGAR,
    APP_TYPE_RAINPOINT,
    CONF_AREA_CODE,
    CONF_EMAIL,
    CONF_HIDS,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .api import HomGarClient, HomGarApiError
from .decoder import decode_payload, get_switch_ports, get_valve_ports
from .telemetry import async_maybe_ping

_LOGGER = logging.getLogger(__name__)


def _extract_state_rssi(raw_state: str | None) -> int | None:
    """Extract RSSI from hub state strings like ``0,-50``."""
    if not raw_state:
        return None
    try:
        parts = str(raw_state).split(",")
        if len(parts) < 2:
            return None
        return int(parts[1])
    except (TypeError, ValueError):
        return None


def _looks_like_device_payload(value: Any) -> bool:
    """Return True for raw device payload frames such as ``10#...``."""
    return isinstance(value, str) and "#" in value


def _select_hub_as_device_status(sub_status: dict[str, dict]) -> dict | None:
    """Find the status entry for a WiFi hub that also acts as a device."""
    for status_id in ("D00", "D0"):
        entry = sub_status.get(status_id)
        if entry and entry.get("value"):
            return entry

    state = sub_status.get("state")
    if state and _looks_like_device_payload(state.get("value")):
        return state

    return None


def _is_empty_hub_placeholder(hub: dict) -> bool:
    """Return True for cloud rows that do not describe a real hub."""
    metadata_fields = (
        "model",
        "displayModel",
        "mac",
    )
    return not any(
        hub.get(field) and str(hub.get(field)).strip().lower() != "unknown"
        for field in metadata_fields
    ) and not hub.get("subDevices")


def _hub_metadata_score(hub: dict) -> int:
    """Prefer complete hub rows over cloud shadow rows."""
    has_model = any(
        hub.get(field) and str(hub.get(field)).strip().lower() != "unknown"
        for field in ("model", "displayModel")
    )
    return (
        (10 if hub.get("subDevices") else 0)
        + (5 if has_model else 0)
        + (3 if hub.get("name") else 0)
        + (2 if hub.get("mac") else 0)
    )


# How many consecutive failed status fetches a hub may coast on last-good data
# before it is finally blanked (→ entities Unavailable). At the 120s poll
# interval this is ~10 minutes: long enough to ride out a passing cloud blip,
# short enough that a genuine outage still surfaces instead of showing stale
# "watering" state forever. See issue #82.
_MAX_STALE_STATUS_POLLS = 5


def _status_on_fetch_failure(
    previous_status: dict | None, consecutive_misses: int, max_misses: int
) -> dict:
    """Choose the status to use for a hub whose status fetch failed this poll.

    A transient failure (e.g. an exhausted 503/timeout) should not immediately
    blank the hub: substituting an empty status list flips every entity on it
    Unavailable for a cycle. Retain the previous poll's status so entities hold
    their last-good values through a passing cloud blip — but only up to
    ``max_misses`` consecutive failures, after which the hub is blanked so a
    genuine, sustained outage stops being masked. Also blanks when there is no
    prior reading. See issue #82.
    """
    if (
        previous_status
        and previous_status.get("subDeviceStatus")
        and consecutive_misses <= max_misses
    ):
        return previous_status
    return {"subDeviceStatus": []}


def _home_names_on_fetch_failure(cached: dict[int, str] | None) -> dict[int, str]:
    """Choose the hid -> homeName map to use when list_homes failed this poll.

    The map was previously rebuilt from scratch each cycle and left empty on
    failure. That is not harmless: ``hub_copy["homeName"]`` falls back to ``""``
    and areas.py skips area seeding entirely for a blank name, so a passing
    cloud blip could quietly suppress it. Retain the last-good map instead.

    Unlike hub status, this needs no staleness cap — a home's name is
    effectively static, so a stale one carries no risk of masking an outage the
    way a stuck "watering" state would. Returns a copy so a later cycle cannot
    mutate the retained map. See issue #82.
    """
    return dict(cached) if cached else {}


def _should_warn_home_name_failure(cached: dict[int, str] | None) -> bool:
    """Whether a failed list_homes fetch deserves a WARNING.

    The client already logs one warning when its retries are exhausted, so
    logging again here made a single blip produce two WARNING entries for the
    same event (reported on issue #82). When a cached map covers the failure
    nothing user-visible degraded, so this drops to debug; a warning is kept
    only when there is genuinely no map to fall back on.
    """
    return not cached


def _hub_identity_keys(hub: dict) -> set[tuple[str, str]]:
    """Return stable cloud identity keys that can reveal duplicate hub rows."""
    keys: set[tuple[str, str]] = set()
    for field in ("deviceName", "iotId"):
        value = hub.get(field)
        if value:
            keys.add((field, str(value)))
    return keys


class HomGarCoordinator(DataUpdateCoordinator):
    """Coordinator for HomGar polling."""

    def __init__(self, hass: HomeAssistant, client: HomGarClient, entry):
        super().__init__(
            hass,
            _LOGGER,
            name="HomGar coordinator",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self._client = client
        self._entry = entry
        self._hids = entry.data.get(CONF_HIDS, [])
        self._notified_unknown_models: set[str] = set()
        self._mqtt_diagnostics: dict[str, dict] = {}
        self._last_good_data: dict[str, dict] = {}
        # Last successful hid -> homeName map, reused when list_homes fails so a
        # blip does not blank home names. See _home_names_on_fetch_failure.
        self._last_good_home_names: dict[int, str] = {}
        # Consecutive failed status fetches per hub mid, used to cap how long a
        # hub may coast on retained last-good status. See _status_on_fetch_failure.
        self._status_miss_count: dict[int, int] = {}
    
    async def handle_mqtt_update(self, data: dict) -> None:
        """Handle MQTT message for real-time valve updates."""
        from .coordinator_mqtt import handle_mqtt_update
        await handle_mqtt_update(self, data)

    def _fire_telemetry_ping(self, hubs: list[dict]) -> None:
        """Fire the opt-in telemetry ping as a background task.

        `async_maybe_ping` already swallows every failure internally and
        must never raise, but everything needed to *schedule* it (resolving
        the shared session, constructing the coroutine, creating the
        background task) happens here too. This is defense in depth: it
        keeps any of that scheduling machinery — not just the ping itself —
        from ever reaching `_async_update_data`'s outer `except Exception`
        and turning a stats hiccup into every entity going Unavailable.
        """
        try:
            result_for_telemetry = {"hubs": hubs}
            self.hass.async_create_background_task(
                async_maybe_ping(
                    self.hass, self._entry, result_for_telemetry,
                    async_get_clientsession(self.hass),
                ),
                name="homgar_telemetry_ping",
            )
        except Exception as err:  # noqa: BLE001 - telemetry must never break the poll
            _LOGGER.debug("Telemetry scheduling failed (ignored): %s", err)

    async def _async_update_data(self):
        """Fetch and decode data from HomGar/RainPoint."""
        try:
            homes = self._hids
            hubs: list[dict] = []
            _LOGGER.debug("Updating data for HIDs: %s", homes)

            # Build hid -> homeName map from the homes list
            home_name_by_hid: dict[int, str] = {}
            try:
                all_homes = await self._client.list_homes()
                for h in all_homes:
                    hid_val = h.get("hid")
                    name_val = h.get("homeName") or h.get("name") or ""
                    if hid_val:
                        home_name_by_hid[int(hid_val)] = name_val
                if home_name_by_hid:
                    self._last_good_home_names = dict(home_name_by_hid)
            except Exception as ex:  # noqa: BLE001
                # Retain the last-good map rather than blanking home names for
                # the cycle, and stay quiet when it covers the blip — the client
                # has already logged its exhausted retries. See issue #82.
                home_name_by_hid = _home_names_on_fetch_failure(
                    self._last_good_home_names
                )
                if _should_warn_home_name_failure(self._last_good_home_names):
                    _LOGGER.warning("HomGar: could not fetch home names: %s", ex)
                else:
                    _LOGGER.debug(
                        "HomGar: could not fetch home names (%s); retaining %d cached name(s)",
                        ex, len(home_name_by_hid),
                    )

            for hid in homes:
                devices = await self._client.get_devices_by_hid(hid)
                _LOGGER.debug("Found %d devices for HID %s: %s", len(devices), hid, [d.get('model', 'unknown') for d in devices])
                seen_hub_keys: set[tuple[str, str]] = set()
                for hub in sorted(devices, key=_hub_metadata_score, reverse=True):
                    if _is_empty_hub_placeholder(hub):
                        _LOGGER.debug(
                            "Skipping empty hub placeholder hid=%s mid=%s",
                            hid,
                            hub.get("mid"),
                        )
                        continue
                    identity_keys = _hub_identity_keys(hub)
                    if identity_keys and seen_hub_keys.intersection(identity_keys):
                        _LOGGER.debug(
                            "Skipping duplicate hub shadow hid=%s mid=%s keys=%s",
                            hid,
                            hub.get("mid"),
                            sorted(identity_keys),
                        )
                        continue
                    seen_hub_keys.update(identity_keys)
                    hub_copy = dict(hub)
                    hub_copy["hid"] = hid
                    hub_copy["homeName"] = home_name_by_hid.get(int(hid), "")
                    hub_copy["brand"] = "RainPoint"
                    hub_model = hub_copy.get("model") or hub_copy.get("displayModel") or "Unknown"
                    hub_copy["model"] = hub_model
                    hub_copy["name"] = (
                        hub_copy.get("name")
                        or hub_copy.get("displayModel")
                        or (hub_model if hub_model != "Unknown" else None)
                        or "RainPoint Hub"
                    )
                    hubs.append(hub_copy)

            # Use efficient multipleDeviceStatus API if available, fall back to individual calls
            status_by_mid: dict[int, dict] = {}
            decoded_sensors: dict[str, dict] = {}
            
            if hubs:
                # Prepare device list for multipleDeviceStatus API
                device_list = []
                for hub in hubs:
                    device_list.append({
                        "mid": hub["mid"],
                        "deviceName": hub.get("deviceName", ""),
                        "productKey": hub.get("productKey", "")
                    })
                
                # Try multipleDeviceStatus first (more efficient)
                try:
                    multiple_status = await self._client.get_multiple_device_status(device_list)
                    _LOGGER.debug("multipleDeviceStatus successful, got data for %d devices", len(multiple_status))
                    
                    # If multipleDeviceStatus returns empty data, fall back to individual calls
                    if not multiple_status:
                        _LOGGER.warning("multipleDeviceStatus returned empty data, falling back to individual calls")
                        raise Exception("Empty response from multipleDeviceStatus")
                    
                    # Convert response to status_by_mid format
                    # Note: get_multiple_device_status already converts "status" to "subDeviceStatus"
                    for device_data in multiple_status:
                        mid = device_data["mid"]
                        status_array = device_data.get("subDeviceStatus", [])
                        status_by_mid[mid] = {"subDeviceStatus": status_array}
                        self._status_miss_count.pop(mid, None)  # fresh reading clears the staleness cap
                        _LOGGER.debug("Fetched status for mid=%s using multipleDeviceStatus", mid)
                        
                except Exception as e:
                    _LOGGER.warning("multipleDeviceStatus failed, falling back to individual calls: %s", e)
                    
                    # Fall back to individual device status calls
                    for hub in hubs:
                        mid = hub["mid"]
                        try:
                            status = await self._client.get_device_status(mid)
                            status_by_mid[mid] = status
                            self._status_miss_count.pop(mid, None)  # fresh reading clears the staleness cap
                            _LOGGER.debug("Fetched status for mid=%s using individual call", mid)
                        except Exception as individual_e:
                            # Transient upstream failure: keep the hub's last-good
                            # status instead of blanking its entities for a cycle,
                            # but only up to _MAX_STALE_STATUS_POLLS so a sustained
                            # outage still surfaces. See issue #82.
                            misses = self._status_miss_count.get(mid, 0) + 1
                            self._status_miss_count[mid] = misses
                            prev = (self.data or {}).get("status", {}).get(mid)
                            retained = _status_on_fetch_failure(prev, misses, _MAX_STALE_STATUS_POLLS)
                            if retained.get("subDeviceStatus"):
                                _LOGGER.warning(
                                    "Failed to get status for mid=%s (miss %d/%d), retaining last-good reading: %s",
                                    mid, misses, _MAX_STALE_STATUS_POLLS, individual_e,
                                )
                            else:
                                _LOGGER.error("Failed to get status for mid=%s: %s", mid, individual_e)
                            status_by_mid[mid] = retained

            for hub in hubs:
                mid = hub["mid"]
                status = status_by_mid.get(mid, {"subDeviceStatus": []})
                hub_state_rssi = _extract_state_rssi(next((entry.get("value") for entry in status.get("subDeviceStatus", []) if entry.get("id") == "state"), None))

                _LOGGER.debug("Processing hub mid=%s with status", mid)

                sub_status = {s["id"]: s for s in status.get("subDeviceStatus", [])}
                _LOGGER.debug("Parsed sub_status for mid=%s: %s keys", mid, len(sub_status))

                # Map addr -> subDevice
                addr_map = {sd["addr"]: sd for sd in hub.get("subDevices", [])}

                for sid, s in sub_status.items():
                    if not sid.startswith("D"):
                        continue
                    addr_str = sid[1:]
                    try:
                        addr = int(addr_str)
                    except ValueError:
                        continue

                    sub = addr_map.get(addr)
                    if not sub:
                        continue

                    raw_value = s.get("value")
                    if not raw_value:
                        # No reading / offline — retain last known good data to avoid spurious unavailable
                        sensor_key_preview = f"{mid}_{addr}"
                        decoded = self._last_good_data.get(sensor_key_preview)
                        _LOGGER.debug("No raw_value for mid=%s addr=%s (sid=%s) — using cached data=%s", mid, addr, sid, decoded is not None)
                    else:
                        model = sub.get("model")
                        try:
                            _LOGGER.debug("Decoding payload for model=%s mid=%s addr=%s: %s", model, mid, addr, raw_value)
                            
                            decoded = decode_payload(model, raw_value)
                            if model == "HWS019WRF-V2":
                                decoded.pop("battery_level", None)
                                if hub_state_rssi is not None:
                                    decoded["signal_strength"] = hub_state_rssi
                            if "error" in decoded:
                                # Model not found in product_models.json
                                decoded = {
                                    "type": "unknown",
                                    "model": model,
                                    "raw_value": raw_value,
                                }
                                _LOGGER.warning(
                                    "="*60 + "\n"
                                    "UNSUPPORTED SENSOR MODEL DETECTED\n"
                                    "Please report this to: https://github.com/brettmeyerowitz/homeassistant-homgar/issues\n"
                                    "Include the following information:\n"
                                    "  Model: %s\n"
                                    "  Device ID (mid): %s\n"
                                    "  Address: %s\n"
                                    "  Raw Payload: %s\n"
                                    + "="*60,
                                    model, mid, addr, raw_value
                                )
                                if model and model not in self._notified_unknown_models:
                                    self._notified_unknown_models.add(model)
                                    async_create(
                                        self.hass,
                                        f"HomGar detected an unsupported sensor model: **{model}**\n\n"
                                        f"To help add support for this sensor, please open an issue at:\n"
                                        f"https://github.com/brettmeyerowitz/homeassistant-homgar/issues\n\n"
                                        f"Include the following raw payload data:\n"
                                        f"```\n{raw_value}\n```\n\n"
                                        f"You can also find this data in the sensor's attributes in Home Assistant.",
                                        title="HomGar: Unsupported Sensor Detected",
                                        notification_id=f"homgar_unsupported_{model}",
                                    )
                            _LOGGER.debug("Decoded data for mid=%s addr=%s: %s", mid, addr, decoded)
                        except Exception as ex:  # noqa: BLE001
                            _LOGGER.warning(
                                "Failed to decode payload for %s addr=%s: %s",
                                model,
                                addr,
                                ex,
                            )
                            decoded = None

                    sensor_key = f"{mid}_{addr}"
                    if decoded and "error" not in decoded:
                        self._last_good_data[sensor_key] = decoded
                    
                    # Extract device timestamp from API response
                    device_time = s.get("time")
                    if device_time:
                        try:
                            dt = datetime.utcfromtimestamp(device_time / 1000).replace(tzinfo=timezone.utc)
                            if decoded:
                                decoded["device_timestamp"] = dt.isoformat()
                                decoded["timestamp_source"] = "device"
                        except (ValueError, TypeError, OSError):
                            pass
                    
                    # Only update data if decoded values have actually changed
                    _SKIP_KEYS = {"device_timestamp", "timestamp_source"}
                    prev_data = (decoded_sensors.get(sensor_key) or {}).get("data") or {}
                    prev_cmp = {k: v for k, v in prev_data.items() if k not in _SKIP_KEYS}
                    new_cmp = {k: v for k, v in (decoded or {}).items() if k not in _SKIP_KEYS}
                    if prev_cmp == new_cmp and sensor_key in decoded_sensors:
                        decoded_sensors[sensor_key]["raw_status"] = s
                    else:
                        decoded_sensors[sensor_key] = {
                            "hid": hub["hid"],
                            "mid": mid,
                            "addr": addr,
                            "home_name": hub.get("homeName"),
                            "hub_name": hub.get("name", "Hub"),
                            "sub_name": sub.get("name"),
                            "port_describe": sub.get("portDescribe"),
                            "model": sub.get("model"),
                            "firmware_version": sub.get("softVer"),
                            "raw_status": s,
                            "data": decoded,
                            "type_flag": sub.get("typeFlag", 0),
                        }

                    _LOGGER.debug("Sensor entity key=%s info=%s", sensor_key, decoded_sensors[sensor_key])

                # Handle WiFi hub-as-device (e.g. HIC801W/HTP159W): the hub
                # itself is a controllable device that never appears in
                # subDevices[]. Status may arrive as D00/D0 or as a raw
                # device payload in state.
                hub_model = hub.get("model") or hub.get("displayModel")
                if hub_model:
                    if get_valve_ports(hub_model) or get_switch_ports(hub_model):
                        hub_device_status = _select_hub_as_device_status(sub_status)
                        if hub_device_status:
                            raw_value = hub_device_status.get("value")
                            decoded = decode_payload(hub_model, raw_value) if raw_value else None
                            sensor_key = f"{mid}_0"
                            if sensor_key not in decoded_sensors:
                                decoded_sensors[sensor_key] = {
                                    "hid": hub["hid"],
                                    "mid": mid,
                                    "addr": 0,
                                    "home_name": hub.get("homeName"),
                                    "hub_name": hub.get("name", "Hub"),
                                    "sub_name": hub.get("name") or hub_model,
                                    "model": hub_model,
                                    "firmware_version": hub.get("softVer"),
                                    "raw_status": hub_device_status,
                                    "data": decoded,
                                    "type_flag": 0,
                                }
                                _LOGGER.debug("Registered hub-as-device sensor key=%s model=%s", sensor_key, hub_model)

            _LOGGER.debug("Coordinator update complete: %d hubs, %d sensors", len(hubs), len(decoded_sensors))
            _LOGGER.debug("Final data: hubs=%s, sensors=%s", hubs, list(decoded_sensors.keys()))
            
            # Update MQTT diagnostics
            self._update_mqtt_diagnostics(hubs)

            # Opt-in telemetry. Off by default; fired in the background (not
            # awaited) so a slow or blackholed telemetry endpoint can never
            # add latency to this poll, and wrapped in its own try/except so
            # nothing telemetry-related can reach the outer `except Exception`
            # below and turn into an UpdateFailed (every entity Unavailable).
            self._fire_telemetry_ping(hubs)

            return {
                "hubs": hubs,
                "status": status_by_mid,
                "sensors": decoded_sensors,
                "mqtt_diagnostics": self._mqtt_diagnostics,
            }
        except HomGarApiError as err:
            raise UpdateFailed(f"HomGar API error: {err}") from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Unexpected HomGar error: {err}") from err

    @property
    def mqtt_connected(self) -> bool:
        """True when the MQTT session is up, regardless of whether any given
        device has emitted a frame yet.

        Read from the live MQTT client rather than the cached per-poll
        diagnostics. The cache is not good enough here: ``async_setup_entry``
        runs the coordinator's first refresh *before* it creates the MQTT
        client, so immediately after a reload the cache is empty and would
        report "not connected" for a full poll interval — which is exactly the
        post-reload window where an automation is most likely to gate a command
        on an idle device's diagnostic entity.

        Entities use this to distinguish "MQTT is down, I cannot tell you"
        (unavailable) from "connected, nothing heard yet" (unknown). Conflating
        the two deadlocked such automations outright. See issue #82.
        """
        client = self._mqtt_client()
        if client is None:
            return False
        connected = getattr(client, "connected", None)
        if connected is None:  # older client object without the property
            try:
                connected = client.get_diagnostics().get("connected")
            except Exception:  # noqa: BLE001 - availability must never raise
                return False
        return bool(connected)

    def _mqtt_client(self):
        """The entry's MQTT client, or None if it has not been created yet."""
        try:
            return (
                self.hass.data.get(DOMAIN, {})
                .get(self._entry.entry_id, {})
                .get("mqtt_client")
            )
        except Exception:  # noqa: BLE001 - availability must never raise
            return None

    def _update_mqtt_diagnostics(self, hubs: list) -> None:
        """Update MQTT diagnostics from MQTT client."""
        try:
            # Get MQTT client from hass data
            mqtt_client = None
            if hasattr(self.hass, 'data') and DOMAIN in self.hass.data:
                entry_data = self.hass.data[DOMAIN].get(self._entry.entry_id, {})
                mqtt_client = entry_data.get("mqtt_client")
            
            if not mqtt_client or not hasattr(mqtt_client, 'get_diagnostics'):
                # Only clear if we previously had data (client removed), not on first poll
                if mqtt_client is not None:
                    self._mqtt_diagnostics.clear()
                return
            
            diagnostics = mqtt_client.get_diagnostics()
            for hub in hubs:
                hub_key = f"rainpoint_hub_{hub.get('mid')}"
                if hub.get("productKey") and hub.get("deviceName"):
                    existing = self._mqtt_diagnostics.get(hub_key, {})
                    self._mqtt_diagnostics[hub_key] = {**existing, **diagnostics}
                else:
                    # Remove diagnostics for hubs without MQTT
                    self._mqtt_diagnostics.pop(hub_key, None)
                    
        except Exception as e:
            _LOGGER.warning("Failed to update MQTT diagnostics: %s", e)
