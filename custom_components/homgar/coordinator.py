import logging
from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from homeassistant.components.persistent_notification import async_create
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DEFAULT_SCAN_INTERVAL,
    CONF_HIDS,
    MODEL_MOISTURE_SIMPLE,
    MODEL_MOISTURE_FULL,
    MODEL_RAIN,
    MODEL_TEMPHUM,
    MODEL_FLOWMETER,
    MODEL_CO2,
    MODEL_POOL,
    MODEL_POOL_PLUS,
    MODEL_DISPLAY_HUB,
    MODEL_VALVE_HUB,
    MODEL_VALVE_213,  # HTV213FRF support
    MODEL_VALVE_245,  # HTV245FRF support
    # New HCS sensor models
    MODEL_HCS005FRF,
    MODEL_HCS003FRF,
    MODEL_HCS024FRF_V1,
    MODEL_HCS015ARF,
    MODEL_HCS0528ARF,
    MODEL_HCS027ARF,
    MODEL_HCS016ARF,
    MODEL_HCS044FRF,
    MODEL_HCS666FRF,
    MODEL_HCS666RFR_P,
    MODEL_HCS999FRF,
    MODEL_HCS999FRF_P,
    MODEL_HCS666FRF_X,
    MODEL_HCS701B,
    MODEL_HCS596WB,
    MODEL_HCS596WB_V4,
    MODEL_HCS706ARF,
    MODEL_HCS802ARF,
    MODEL_HCS048B,
    MODEL_HCS888ARF_V1,
    MODEL_HCS0600ARF,
)
from .homgar_api import (
    HomGarClient, HomGarApiError,
    decode_moisture_simple, decode_moisture_full, decode_rain,
    decode_temphum, decode_flowmeter, decode_co2, decode_pool, decode_pool_plus,
    decode_valve_hub, decode_htv213frf_valve,
    # New HCS decoder functions
    decode_hcs005frf, decode_hcs003frf, decode_hcs024frf_v1,
    decode_hcs015arf, decode_hcs0528arf, decode_hcs027arf, decode_hcs016arf,
    decode_hcs044frf, decode_hcs666frf, decode_hcs666rfr_p, decode_hcs999frf,
    decode_hcs999frf_p, decode_hcs666frf_x, decode_hcs701b, decode_hcs596wb,
    decode_hcs596wb_v4, decode_hcs706arf, decode_hcs802arf, decode_hcs048b,
    decode_hcs888arf_v1, decode_hcs0600arf,
    VERSION, debug_with_version,
)

_LOGGER = logging.getLogger(__name__)

# Decoder registry - maps device models to their decoder functions
DECODER_REGISTRY = {
    MODEL_MOISTURE_SIMPLE: decode_moisture_simple,
    MODEL_MOISTURE_FULL: decode_moisture_full,
    MODEL_RAIN: decode_rain,
    MODEL_TEMPHUM: decode_temphum,
    MODEL_FLOWMETER: decode_flowmeter,
    MODEL_CO2: decode_co2,
    MODEL_POOL: decode_pool,
    MODEL_POOL_PLUS: decode_pool_plus,
    MODEL_VALVE_HUB: decode_valve_hub,
    MODEL_VALVE_213: decode_htv213frf_valve,  # HTV213FRF uses custom decoder
    MODEL_VALVE_245: decode_htv213frf_valve,  # HTV245FRF uses custom decoder
    # HCS sensor models (v1.3.0)
    MODEL_HCS005FRF: decode_hcs005frf,
    MODEL_HCS003FRF: decode_hcs003frf,
    MODEL_HCS024FRF_V1: decode_hcs024frf_v1,
    MODEL_HCS015ARF: decode_hcs015arf,
    MODEL_HCS0528ARF: decode_hcs0528arf,
    MODEL_HCS027ARF: decode_hcs027arf,
    MODEL_HCS016ARF: decode_hcs016arf,
    MODEL_HCS044FRF: decode_hcs044frf,
    MODEL_HCS666FRF: decode_hcs666frf,
    MODEL_HCS666RFR_P: decode_hcs666rfr_p,
    MODEL_HCS999FRF: decode_hcs999frf,
    MODEL_HCS999FRF_P: decode_hcs999frf_p,
    MODEL_HCS666FRF_X: decode_hcs666frf_x,
    MODEL_HCS701B: decode_hcs701b,
    MODEL_HCS596WB: decode_hcs596wb,
    MODEL_HCS596WB_V4: decode_hcs596wb_v4,
    MODEL_HCS706ARF: decode_hcs706arf,
    MODEL_HCS802ARF: decode_hcs802arf,
    MODEL_HCS048B: decode_hcs048b,
    MODEL_HCS888ARF_V1: decode_hcs888arf_v1,
    MODEL_HCS0600ARF: decode_hcs0600arf,
}


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

    async def _async_update_data(self):
        """Fetch and decode data from HomGar/RainPoint."""
        try:
            homes = self._hids
            hubs: list[dict] = []
            _LOGGER.info("Updating data for HIDs: %s", homes)
            for hid in homes:
                devices = await self._client.get_devices_by_hid(hid)
                _LOGGER.info("Found %d devices for HID %s: %s", len(devices), hid, [d.get('model', 'unknown') for d in devices])
                for hub in devices:
                    hub_copy = dict(hub)
                    hub_copy["hid"] = hid
                    # All devices are RainPoint hardware
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
                    _LOGGER.debug(debug_with_version("multipleDeviceStatus successful, got data for %d devices"), len(multiple_status))
                    
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
                        _LOGGER.debug(debug_with_version("Fetched status for mid=%s using multipleDeviceStatus"), mid)
                        
                except Exception as e:
                    _LOGGER.warning("multipleDeviceStatus failed, falling back to individual calls: %s", e)
                    
                    # Fall back to individual device status calls
                    for hub in hubs:
                        mid = hub["mid"]
                        try:
                            status = await self._client.get_device_status(mid)
                            status_by_mid[mid] = status
                            _LOGGER.debug(debug_with_version("Fetched status for mid=%s using individual call"), mid)
                        except Exception as individual_e:
                            _LOGGER.error("Failed to get status for mid=%s: %s", mid, individual_e)
                            status_by_mid[mid] = {"subDeviceStatus": []}

            for hub in hubs:
                mid = hub["mid"]
                status = status_by_mid.get(mid, {"subDeviceStatus": []})

                _LOGGER.debug(debug_with_version("Processing hub mid=%s with status"), mid)

                sub_status = {s["id"]: s for s in status.get("subDeviceStatus", [])}
                _LOGGER.debug(debug_with_version("Parsed sub_status for mid=%s: %s keys"), mid, len(sub_status))

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
                            _LOGGER.debug(debug_with_version("Decoding payload for model=%s mid=%s addr=%s: %s"), model, mid, addr, raw_value)
                            
                            # Special case: Display Hub uses different decoder
                            if model == MODEL_DISPLAY_HUB:
                                from .homgar_api import decode_hws019wrf_v2
                                decoded = decode_hws019wrf_v2(raw_value)
                            else:
                                # Use decoder registry for all other models
                                decoder_func = DECODER_REGISTRY.get(model)
                                if decoder_func:
                                    decoded = decoder_func(raw_value)
                                else:
                                    # Unknown model - store raw data for reporting
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
                                    # Send persistent notification (once per model)
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
                            _LOGGER.debug(debug_with_version("Decoded data for mid=%s addr=%s: %s"), mid, addr, decoded)
                        except Exception as ex:  # noqa: BLE001
                            _LOGGER.warning(
                                "Failed to decode payload for %s addr=%s: %s",
                                model,
                                addr,
                                ex,
                            )
                            decoded = None

                    sensor_key = f"{hub['hid']}_{mid}_{addr}"
                    
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
                    }

                    _LOGGER.debug(debug_with_version("Sensor entity key=%s info=%s"), sensor_key, decoded_sensors[sensor_key])

            _LOGGER.info("Coordinator update complete: %d hubs, %d sensors", len(hubs), len(decoded_sensors))
            _LOGGER.debug(debug_with_version("Final data: hubs=%s, sensors=%s"), hubs, list(decoded_sensors.keys()))
            
            return {
                "hubs": hubs,
                "status": status_by_mid,
                "sensors": decoded_sensors,
            }
        except HomGarApiError as err:
            raise UpdateFailed(f"HomGar API error: {err}") from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Unexpected HomGar error: {err}") from err