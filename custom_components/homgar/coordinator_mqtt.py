"""MQTT integration for HomGar coordinator - handles real-time valve updates."""
import logging
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
        _LOGGER.debug("HomGar MQTT: Hub mid=%s not found in coordinator data", hub_mid)
        return
    
    # Extract address from device_key (D01 -> addr 1, D02 -> addr 2, etc.)
    try:
        addr = int(device_key[1:])
    except (ValueError, IndexError):
        _LOGGER.warning("HomGar MQTT: Invalid device_key format: %s", device_key)
        return
    
    _LOGGER.info(
        "HomGar MQTT: Processing valve update for hub_mid=%s addr=%d model=%s",
        hub_mid,
        addr,
        target_hub.get("model"),
    )
    
    # Decode the payload using the same decoder as REST API
    from .homgar_api import decode_valve_hub, decode_htv213frf_valve
    from .const import MODEL_VALVE_HUB, MODEL_VALVE_213, MODEL_VALVE_245
    
    model = target_hub.get("model")
    decoder = None
    
    if model == MODEL_VALVE_HUB:
        decoder = decode_valve_hub
    elif model in (MODEL_VALVE_213, MODEL_VALVE_245):
        decoder = decode_htv213frf_valve
    
    if not decoder:
        _LOGGER.debug("HomGar MQTT: No valve decoder for model=%s", model)
        return
    
    try:
        decoded = decoder(payload)
        _LOGGER.info(
            "HomGar MQTT: Decoded valve state for hub_mid=%s addr=%d: %s",
            hub_mid,
            addr,
            decoded,
        )
        
        # Update the sensor data in coordinator
        sensor_key = f"{hub_mid}_{addr}"
        decoded_sensors = coordinator.data.get("sensors", {})
        
        if sensor_key in decoded_sensors:
            # Update existing sensor data
            decoded_sensors[sensor_key]["data"] = decoded
            decoded_sensors[sensor_key]["raw_status"]["value"] = payload
            
            _LOGGER.info(
                "HomGar MQTT: Updated sensor %s with real-time data (valve state: %s)",
                sensor_key,
                "OPEN" if decoded.get("zones", {}).get(addr, {}).get("open") else "CLOSED",
            )
            
            # Trigger coordinator update to notify entities
            coordinator.async_set_updated_data(coordinator.data)
        else:
            _LOGGER.debug("HomGar MQTT: Sensor key %s not found in coordinator data", sensor_key)
    
    except Exception as e:
        _LOGGER.error("HomGar MQTT: Failed to decode valve payload: %s", e, exc_info=True)
