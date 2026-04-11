import logging
from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from homeassistant.components.persistent_notification import async_create
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
from .homgar_api import HomGarClient, HomGarApiError
from .decoder import decode_payload, get_valve_ports

_LOGGER = logging.getLogger(__name__)


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
    
    async def handle_mqtt_update(self, data: dict) -> None:
        """Handle MQTT message for real-time valve updates."""
        from .coordinator_mqtt import handle_mqtt_update
        await handle_mqtt_update(self, data)

    async def _async_update_data(self):
        """Fetch and decode data from HomGar/RainPoint."""
        try:
            homes = self._hids
            hubs: list[dict] = []
            _LOGGER.info("Updating data for HIDs: %s", homes)

            # Build hid -> homeName map from the homes list
            home_name_by_hid: dict[int, str] = {}
            try:
                all_homes = await self._client.list_homes()
                for h in all_homes:
                    hid_val = h.get("hid")
                    name_val = h.get("homeName") or h.get("name") or ""
                    if hid_val:
                        home_name_by_hid[int(hid_val)] = name_val
            except Exception as ex:  # noqa: BLE001
                _LOGGER.warning("HomGar: could not fetch home names: %s", ex)

            for hid in homes:
                devices = await self._client.get_devices_by_hid(hid)
                _LOGGER.info("Found %d devices for HID %s: %s", len(devices), hid, [d.get('model', 'unknown') for d in devices])
                for hub in devices:
                    hub_copy = dict(hub)
                    hub_copy["hid"] = hid
                    hub_copy["homeName"] = home_name_by_hid.get(int(hid), "")
                    hub_copy["brand"] = "RainPoint"
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
                        _LOGGER.debug("Fetched status for mid=%s using multipleDeviceStatus", mid)
                        
                except Exception as e:
                    _LOGGER.warning("multipleDeviceStatus failed, falling back to individual calls: %s", e)
                    
                    # Fall back to individual device status calls
                    for hub in hubs:
                        mid = hub["mid"]
                        try:
                            status = await self._client.get_device_status(mid)
                            status_by_mid[mid] = status
                            _LOGGER.debug("Fetched status for mid=%s using individual call", mid)
                        except Exception as individual_e:
                            _LOGGER.error("Failed to get status for mid=%s: %s", mid, individual_e)
                            status_by_mid[mid] = {"subDeviceStatus": []}

            for hub in hubs:
                mid = hub["mid"]
                status = status_by_mid.get(mid, {"subDeviceStatus": []})

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
                        # No reading / offline
                        decoded = None
                        _LOGGER.debug("No raw_value for mid=%s addr=%s (sid=%s)", mid, addr, sid)
                    else:
                        model = sub.get("model")
                        try:
                            _LOGGER.debug("Decoding payload for model=%s mid=%s addr=%s: %s", model, mid, addr, raw_value)
                            
                            decoded = decode_payload(model, raw_value)
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
                    
                    decoded_sensors[sensor_key] = {
                        "hid": hub["hid"],
                        "mid": mid,
                        "addr": addr,
                        "home_name": hub.get("homeName"),
                        "hub_name": hub.get("name", "Hub"),
                        "sub_name": sub.get("name"),
                        "model": sub.get("model"),
                        "firmware_version": sub.get("softVer"),
                        "raw_status": s,
                        "data": decoded,
                        "type_flag": sub.get("typeFlag", 0),
                    }

                    _LOGGER.debug("Sensor entity key=%s info=%s", sensor_key, decoded_sensors[sensor_key])

                # Handle WiFi hub-as-device (e.g. HIC801W): the hub itself is a
                # controllable device whose status arrives as D00 in subDeviceStatus.
                # It never appears in subDevices[], so the loop above skips it.
                hub_model = hub.get("model") or hub.get("displayModel")
                if hub_model:
                    if get_valve_ports(hub_model):
                        d00 = sub_status.get("D00") or sub_status.get("D0")
                        if d00:
                            raw_value = d00.get("value")
                            decoded = decode_payload(hub_model, raw_value) if raw_value else None
                            sensor_key = f"{mid}_0"
                            if sensor_key not in decoded_sensors:
                                decoded_sensors[sensor_key] = {
                                    "hid": hub["hid"],
                                    "mid": mid,
                                    "addr": 0,
                                    "home_name": hub.get("homeName"),
                                    "hub_name": hub.get("name", "Hub"),
                                    "sub_name": hub.get("name", hub_model),
                                    "model": hub_model,
                                    "firmware_version": hub.get("softVer"),
                                    "raw_status": d00,
                                    "data": decoded,
                                    "type_flag": 0,
                                }
                                _LOGGER.debug("Registered hub-as-device sensor key=%s model=%s", sensor_key, hub_model)

            _LOGGER.info("Coordinator update complete: %d hubs, %d sensors", len(hubs), len(decoded_sensors))
            _LOGGER.debug("Final data: hubs=%s, sensors=%s", hubs, list(decoded_sensors.keys()))
            
            # Update MQTT diagnostics
            self._update_mqtt_diagnostics(hubs)
            
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
                    self._mqtt_diagnostics[hub_key] = diagnostics
                else:
                    # Remove diagnostics for hubs without MQTT
                    self._mqtt_diagnostics.pop(hub_key, None)
                    
        except Exception as e:
            _LOGGER.warning("Failed to update MQTT diagnostics: %s", e)