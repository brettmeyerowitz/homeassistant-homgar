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
    hub_state = data.get("hub_state")
    
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
    now_iso = datetime.now(timezone.utc).isoformat()

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

    hub_diag_key = f"rainpoint_hub_{matched_mid}"
    hub_diag = dict(coordinator._mqtt_diagnostics.get(hub_diag_key) or {})
    hub_diag.update(
        {
            "raw_payload": payload,
            "friendly_summary": f"{device_key}: payload received",
            "last_received": now_iso,
            "device_key": device_key,
            "hub_mid": matched_mid,
        }
    )
    coordinator._mqtt_diagnostics[hub_diag_key] = hub_diag
    
    _LOGGER.debug(
        "HomGar MQTT: Processing update for hub_mid=%s name=%s addr=%d model=%s",
        matched_mid,
        hub_name,
        addr,
        target_hub.get("model"),
    )
    
    from .decoder import decode_payload
    from .const import get_port_label

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
        if model == "HWS019WRF-V2":
            decoded.pop("battery_level", None)
            try:
                if hub_state:
                    parts = str(hub_state).split(",")
                    if len(parts) >= 2:
                        decoded["signal_strength"] = int(parts[1])
            except (TypeError, ValueError):
                pass
        if "error" in decoded:
            _LOGGER.debug("HomGar MQTT: No decoder for model=%s (sub_model=%s)", model, sub_model)
            coordinator.async_set_updated_data(coordinator.data)
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
                elif "rain_detected" in decoded:
                    status_msg = "Rained" if decoded.get("rain_detected") else "Not rained"
                elif "temperature" in decoded:
                    status_msg = f"Temp: {decoded.get('temperature')}°C"
                else:
                    status_msg = "data updated"

            friendly_parts = []

            def _append_scalar_parts(source: dict, prefix: str = "") -> None:
                label_prefix = f"{prefix} " if prefix else ""
                if "battery_level" in source:
                    friendly_parts.append(f"{label_prefix}battery {source['battery_level']}%")
                if "signal_strength" in source:
                    friendly_parts.append(f"{label_prefix}RSSI {source['signal_strength']} dBm")
                if "temperature" in source:
                    friendly_parts.append(f"{label_prefix}temp {source['temperature']}°C")
                if "humidity" in source:
                    friendly_parts.append(f"{label_prefix}humidity {source['humidity']}%")
                if "soil_moisture" in source:
                    friendly_parts.append(f"{label_prefix}soil {source['soil_moisture']}%")
                if "rain_detected" in source:
                    friendly_parts.append(
                        f"{label_prefix}rain {'rained' if source['rain_detected'] else 'not rained'}"
                    )
                if "carbon_dioxide" in source:
                    friendly_parts.append(f"{label_prefix}CO₂ {source['carbon_dioxide']} ppm")
                if "air_pressure" in source:
                    friendly_parts.append(f"{label_prefix}pressure {source['air_pressure']} hPa")
                if "illuminance" in source:
                    friendly_parts.append(f"{label_prefix}illuminance {source['illuminance']} lx")
                if "current_water_volume" in source:
                    friendly_parts.append(f"{label_prefix}current volume {source['current_water_volume']} L")
                if "last_water_volume" in source:
                    friendly_parts.append(f"{label_prefix}last volume {source['last_water_volume']} L")
                if "today_water_volume" in source:
                    friendly_parts.append(f"{label_prefix}today volume {source['today_water_volume']} L")
                if "total_water_volume" in source:
                    friendly_parts.append(f"{label_prefix}total volume {source['total_water_volume']} L")
                if "flow_rate" in source:
                    unit = source.get("flow_rate_unit", "L/min")
                    friendly_parts.append(f"{label_prefix}flow {source['flow_rate']} {unit}")
                if "current_session_duration" in source:
                    friendly_parts.append(f"{label_prefix}session {source['current_session_duration']}s")
                if "last_water_duration" in source:
                    friendly_parts.append(f"{label_prefix}last duration {source['last_water_duration']}s")
                if "event_time" in source:
                    friendly_parts.append(f"{label_prefix}event {source['event_time']}")
                if "event_time2" in source:
                    friendly_parts.append(f"{label_prefix}event end {source['event_time2']}")
                if "irrigation_end_time" in source:
                    friendly_parts.append(f"{label_prefix}irrigation end {source['irrigation_end_time']}")
                if "cycle_type" in source:
                    friendly_parts.append(f"{label_prefix}cycle type {source['cycle_type']}")

            _append_scalar_parts(decoded)
            for p in range(1, decoded.get("port_number", 1) + 1):
                port = decoded.get(f"port_{p}", {})
                if port.get("valve_state"):
                    label = get_port_label(decoded_sensors[sensor_key], p) or f"zone {p}"
                    friendly_parts.append(f"{label}: {port['valve_state']}")
                _append_scalar_parts(port, get_port_label(decoded_sensors[sensor_key], p) or f"zone {p}")

            # Always refresh MQTT diagnostics even when the decoded data is unchanged.
            decoded_sensors[sensor_key]["raw_status"]["value"] = payload
            coordinator._mqtt_diagnostics[sensor_key] = {
                "raw_payload": payload,
                "friendly_summary": ", ".join(friendly_parts) if friendly_parts else "data updated",
                "last_received": now_iso,
            }

            # Skip state update if decoded data is identical to what's already stored
            existing = decoded_sensors[sensor_key].get("data") or {}
            _SKIP_KEYS = {"device_timestamp", "timestamp_source"}
            existing_cmp = {k: v for k, v in existing.items() if k not in _SKIP_KEYS}
            decoded_cmp = {k: v for k, v in decoded.items() if k not in _SKIP_KEYS}
            if existing_cmp == decoded_cmp:
                _LOGGER.debug(
                    "HomGar MQTT: No change in data for sensor %s — refreshed MQTT diagnostics only",
                    sensor_key,
                )
                coordinator.async_set_updated_data(coordinator.data)
                return

            # Stamp with current time and mark as MQTT-sourced
            decoded["device_timestamp"] = now_iso
            decoded["timestamp_source"] = "mqtt"

            # Update existing sensor data
            decoded_sensors[sensor_key]["data"] = decoded

            # Keep last-good cache in sync so REST null responses don't clobber fresh MQTT data
            coordinator._last_good_data[sensor_key] = decoded
            _LOGGER.debug(
                "HomGar MQTT: Updated sensor %s (%s / %s) with real-time data (%s)",
                sensor_key,
                hub_name,
                sub_name or model,
                status_msg,
            )

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
            coordinator.async_set_updated_data(coordinator.data)
    
    except Exception as e:
        _LOGGER.error("HomGar MQTT: Failed to decode payload: %s", e, exc_info=True)
