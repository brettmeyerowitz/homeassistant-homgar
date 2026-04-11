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
    device_key = data.get("device_key")  # e.g., "D01", "D02"
    payload = data.get("payload")  # e.g., "11#00..."
    
    _LOGGER.info(
        "HomGar MQTT update received: hub_mid=%s device_key=%s payload=%s",
        hub_mid,
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
        if str(hub.get("mid")) == str(hub_mid):
            target_hub = hub
            break
    
    if not target_hub:
        # Log available hubs for debugging
        available_mids = [str(h.get("mid")) for h in hubs]
        _LOGGER.warning(
            "HomGar MQTT: Hub mid=%s not found. Available hubs: %s",
            hub_mid,
            available_mids
        )
        return
    
    _LOGGER.debug(
        "HomGar MQTT: Found hub mid=%s model=%s sub_devices=%d",
        hub_mid,
        target_hub.get("model"),
        len(target_hub.get("subDevices", []))
    )
    
    # Extract address from device_key (D01 -> addr 1, D02 -> addr 2, etc.)
    try:
        addr = int(device_key[1:])
    except (ValueError, IndexError):
        _LOGGER.warning("HomGar MQTT: Invalid device_key format: %s", device_key)
        return
    
    _LOGGER.info(
        "HomGar MQTT: Processing update for hub_mid=%s addr=%d model=%s",
        hub_mid,
        addr,
        target_hub.get("model"),
    )
    
    from .decoder import decode_payload

    # Find sub-device model by addr in hub's subDevices list
    sub_devices = target_hub.get("subDevices", [])
    sub_model = None
    for sub in sub_devices:
        if sub.get("addr") == addr:
            sub_model = sub.get("model")
            break
    
    _LOGGER.debug(
        "HomGar MQTT: Sub-device lookup addr=%d found=%s sub_model=%s",
        addr,
        sub_model is not None,
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
        _LOGGER.info(
            "HomGar MQTT: Decoded model=%s for hub_mid=%s addr=%d fields=%s",
            model,
            hub_mid,
            addr,
            top_fields,
        )
        
        # Update the sensor data in coordinator
        sensor_key = f"{hub_mid}_{addr}"
        decoded_sensors = coordinator.data.get("sensors", {})
        
        if sensor_key in decoded_sensors:
            # Stamp with current time and mark as MQTT-sourced
            now_iso = datetime.now(timezone.utc).isoformat()
            decoded["device_timestamp"] = now_iso
            decoded["timestamp_source"] = "mqtt"

            # Update existing sensor data
            decoded_sensors[sensor_key]["data"] = decoded
            decoded_sensors[sensor_key]["raw_status"]["value"] = payload
            
            # Determine status message based on decoded fields (v3 field names)
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
            
            _LOGGER.info(
                "HomGar MQTT: Updated sensor %s with real-time data (%s)",
                sensor_key,
                status_msg,
            )
            
            # Trigger coordinator update to notify entities
            coordinator.async_set_updated_data(coordinator.data)
        else:
            # Log available sensor keys for debugging
            available_keys = list(decoded_sensors.keys())
            _LOGGER.warning(
                "HomGar MQTT: Sensor key %s not found. Available keys: %s",
                sensor_key,
                available_keys
            )
    
    except Exception as e:
        _LOGGER.error("HomGar MQTT: Failed to decode payload: %s", e, exc_info=True)
