import logging
from datetime import timedelta

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
)
from .homgar_api import (
    HomGarClient, HomGarApiError,
    decode_moisture_simple, decode_moisture_full, decode_rain,
    decode_temphum, decode_flowmeter, decode_co2, decode_pool, decode_pool_plus,
)

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
                    # Use app_type to determine brand
                    if self._client._app_type == "rainpoint":
                        brand = "RainPoint"
                    else:
                        brand = "HomGar"
                    hub_copy["brand"] = brand
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
                    for device_data in multiple_status:
                        mid = device_data["mid"]
                        status_by_mid[mid] = {"subDeviceStatus": device_data.get("status", [])}
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
                            if model == MODEL_MOISTURE_SIMPLE:
                                decoded = decode_moisture_simple(raw_value)
                            elif model == MODEL_MOISTURE_FULL:
                                decoded = decode_moisture_full(raw_value)
                            elif model == MODEL_RAIN:
                                decoded = decode_rain(raw_value)
                            elif model == MODEL_TEMPHUM:
                                decoded = decode_temphum(raw_value)
                            elif model == MODEL_FLOWMETER:
                                decoded = decode_flowmeter(raw_value)
                            elif model == MODEL_CO2:
                                decoded = decode_co2(raw_value)
                            elif model == MODEL_POOL:
                                decoded = decode_pool(raw_value)
                            elif model == MODEL_POOL_PLUS:
                                decoded = decode_pool_plus(raw_value)
                            elif model == MODEL_DISPLAY_HUB:
                                from .homgar_api import decode_hws019wrf_v2
                                decoded = decode_hws019wrf_v2(raw_value)
                            else:
                                # Store raw data for unknown models so users can report it
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
                            _LOGGER.debug("Decoded data for mid=%s addr=%s: %s", mid, addr, decoded)
                        except Exception as ex:  # noqa: BLE001
                            _LOGGER.warning(
                                "Failed to decode payload for %s addr=%s: %s",
                                model,
                                addr,
                                ex,
                            )
                            decoded = None

                    sensor_key = f"{hub['hid']}_{mid}_{addr}"
                    decoded_sensors[sensor_key] = {
                        "hid": hub["hid"],
                        "mid": mid,
                        "addr": addr,
                        "home_name": hub.get("homeName"),  # may not be present
                        "hub_name": hub.get("name", "Hub"),
                        "sub_name": sub.get("name"),
                        "model": sub.get("model"),
                        "raw_status": s,
                        "data": decoded,
                    }

                    _LOGGER.debug("Sensor entity key=%s info=%s", sensor_key, decoded_sensors[sensor_key])

            _LOGGER.info("Coordinator update complete: %d hubs, %d sensors", len(hubs), len(decoded_sensors))
            _LOGGER.debug("Final data: hubs=%s, sensors=%s", hubs, list(decoded_sensors.keys()))
            
            return {
                "hubs": hubs,
                "status": status_by_mid,
                "sensors": decoded_sensors,
            }
        except HomGarApiError as err:
            raise UpdateFailed(f"HomGar API error: {err}") from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Unexpected HomGar error: {err}") from err