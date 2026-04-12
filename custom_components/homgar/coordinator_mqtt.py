"""MQTT integration for HomGar coordinator - handles real-time device updates.

Supports all device types: valves, sensors, flow meters, CO2 monitors, etc.
"""
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import HomGarCoordinator

_LOGGER = logging.getLogger(__name__)


async def handle_mqtt_update(coordinator: "HomGarCoordinator", data: dict) -> None:
    """Handle MQTT message and update coordinator data.
    
    Args:
        coordinator: The HomGarCoordinator instance
        data: MQTT message data with keys: hub_mid, device_key, payload
    """
    hub_mid = data.get("hub_mid")
    hub_mid_candidates = data.get("hub_mid_candidates") or [hub_mid]
    device_key = data.get("device_key")  # e.g., "D01", "D02"
    payload = data.get("payload")  # e.g., "11#00..."
    
    _LOGGER.debug(
        "HomGar MQTT update received: hub_mid=%s candidates=%s device_key=%s payload=%s",
        hub_mid,
        hub_mid_candidates,
        device_key,
        payload[:50] if payload else None,
    )
    
    if not coordinator.data:
        _LOGGER.debug("HomGar MQTT: No coordinator data yet, skipping update")
        return
    
    # Find the hub with this MID
    hubs = coordinator.data.get("hubs", [])
    target_hub = None
    for hub in hubs:
        if str(hub.get("mid")) in {str(c) for c in hub_mid_candidates if c is not None}:
            target_hub = hub
            break
    
    if not target_hub:
        # Log available hubs for debugging
        available_mids = [str(h.get("mid")) for h in hubs]
        _LOGGER.warning(
            "HomGar MQTT: Hub mid=%s candidates=%s not found. Available hubs: %s",
            hub_mid,
            hub_mid_candidates,
            available_mids
        )
        return

    matched_mid = str(target_hub.get("mid"))
    hub_name = target_hub.get("name", "Hub")

    _LOGGER.debug(
        "HomGar MQTT: Found hub mid=%s name=%s model=%s sub_devices=%d",
        matched_mid,
        hub_name,
        target_hub.get("model"),
        len(target_hub.get("subDevices", []))
    )
    
    # Extract address from device_key (D01 -> addr 1, D02 -> addr 2, etc.)
    try:
        addr = int(device_key[1:])
    except (ValueError, IndexError):
        _LOGGER.warning("HomGar MQTT: Invalid device_key format: %s", device_key)
        return
    
    _LOGGER.debug(
        "HomGar MQTT: Processing update for hub_mid=%s name=%s addr=%d model=%s",
        matched_mid,
        hub_name,
        addr,
        target_hub.get("model"),
    )
    
    from .decoder import decode_payload

    # Find sub-device model by addr in hub's subDevices list
    sub_devices = target_hub.get("subDevices", [])
    sub_model = None
    sub_name = None
    for sub in sub_devices:
        if sub.get("addr") == addr:
            sub_model = sub.get("model")
            sub_name = sub.get("name")
            break

    if addr == 0:
        sub_name = target_hub.get("name", target_hub.get("model"))

    _LOGGER.debug(
        "HomGar MQTT: Sub-device lookup addr=%d found=%s sub_name=%s sub_model=%s",
        addr,
        sub_model is not None,
        sub_name,
        sub_model,
    )

    # Fall back to hub model if no sub-device match
    model = sub_model or target_hub.get("model")

    try:
        decoded = decode_payload(model, payload)
        if "error" in decoded:
            _LOGGER.debug("HomGar MQTT: No decoder for model=%s (sub_model=%s)", model, sub_model)
            return
        top_fields = [k for k in decoded if not k.startswith("port_") and k not in ("port_number", "dp_flag")]
        _LOGGER.debug(
            "HomGar MQTT: Decoded model=%s for hub_mid=%s name=%s addr=%d sub_name=%s fields=%s",
            model,
            matched_mid,
            hub_name,
            addr,
            sub_name,
            top_fields,
        )
        
        # Update the sensor data in coordinator
        sensor_key = f"{matched_mid}_{addr}"
        decoded_sensors = coordinator.data.get("sensors", {})
        
        if sensor_key in decoded_sensors:
            # Skip update if decoded data is identical to what's already stored
            existing = decoded_sensors[sensor_key].get("data") or {}
            _SKIP_KEYS = {"device_timestamp", "timestamp_source"}
            existing_cmp = {k: v for k, v in existing.items() if k not in _SKIP_KEYS}
            decoded_cmp = {k: v for k, v in decoded.items() if k not in _SKIP_KEYS}
            if existing_cmp == decoded_cmp:
                _LOGGER.debug(
                    "HomGar MQTT: No change in data for sensor %s — skipping update",
                    sensor_key,
                )
                return

            # Stamp with current time and mark as MQTT-sourced
            now_iso = datetime.now(timezone.utc).isoformat()
            decoded["device_timestamp"] = now_iso
            decoded["timestamp_source"] = "mqtt"

            # Update existing sensor data
            decoded_sensors[sensor_key]["data"] = decoded
            decoded_sensors[sensor_key]["raw_status"]["value"] = payload

            # Keep last-good cache in sync so REST null responses don't clobber fresh MQTT data
            coordinator._last_good_data[sensor_key] = decoded
            
            # Determine status message based on decoded fields (v3 field names)
            watering_ports = [
                p
                for p in range(1, decoded.get("port_number", 1) + 1)
                if decoded.get(f"port_{p}", {}).get("is_watering")
            ]
            if watering_ports:
                status_msg = f"zone {watering_ports[0]}: irrigation"
            else:
                port1 = decoded.get("port_1", {})
                if port1.get("valve_state") is not None:
                    status_msg = f"valve state: {port1.get('valve_state', 'unknown')}"
                elif "carbon_dioxide" in decoded:
                    status_msg = f"CO2: {decoded.get('carbon_dioxide')} ppm"
                elif "total_water_volume" in decoded:
                    status_msg = f"Total flow: {decoded.get('total_water_volume')} L"
                elif "soil_moisture" in decoded:
                    status_msg = f"Moisture: {decoded.get('soil_moisture')}%"
                elif "temperature" in decoded:
                    status_msg = f"Temp: {decoded.get('temperature')}°C"
                else:
                    status_msg = "data updated"
            
            _LOGGER.debug(
                "HomGar MQTT: Updated sensor %s (%s / %s) with real-time data (%s)",
                sensor_key,
                hub_name,
                sub_name or model,
                status_msg,
            )
            
            # Store MQTT diagnostics for diagnostic sensor entities
            friendly_parts = []
            if "battery_level" in decoded:
                friendly_parts.append(f"battery {decoded['battery_level']}%")
            if "signal_strength" in decoded:
                friendly_parts.append(f"RSSI {decoded['signal_strength']} dBm")
            if "temperature" in decoded:
                friendly_parts.append(f"temp {decoded['temperature']}°C")
            if "humidity" in decoded:
                friendly_parts.append(f"humidity {decoded['humidity']}%")
            if "soil_moisture" in decoded:
                friendly_parts.append(f"soil {decoded['soil_moisture']}%")
            if "carbon_dioxide" in decoded:
                friendly_parts.append(f"CO₂ {decoded['carbon_dioxide']} ppm")
            if "air_pressure" in decoded:
                friendly_parts.append(f"pressure {decoded['air_pressure']} hPa")
            if "total_water_volume" in decoded:
                friendly_parts.append(f"total flow {decoded['total_water_volume']} L")
            for p in range(1, decoded.get("port_number", 1) + 1):
                port = decoded.get(f"port_{p}", {})
                if port.get("valve_state"):
                    friendly_parts.append(f"zone {p}: {port['valve_state']}")
            coordinator._mqtt_diagnostics[sensor_key] = {
                "raw_payload": payload,
                "friendly_summary": ", ".join(friendly_parts) if friendly_parts else "data updated",
                "last_received": now_iso,
            }

            # Trigger coordinator update to notify entities
            coordinator.async_set_updated_data(coordinator.data)
        else:
            # Log available sensor keys for debugging
            available_keys = list(decoded_sensors.keys())
            _LOGGER.warning(
                "HomGar MQTT: Sensor key %s (%s / %s) not found. Available keys: %s",
                sensor_key,
                hub_name,
                sub_name or model,
                available_keys
            )
    
    except Exception as e:
        _LOGGER.error("HomGar MQTT: Failed to decode payload: %s", e, exc_info=True)
