"""Diagnostic sensors for HomGar devices."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, PERCENTAGE
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HomGarCoordinator


class HomGarDiagnosticSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for HomGar diagnostic sensors."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: HomGarCoordinator,
        sensor_key: str,
        sensor_info: dict,
        base_slug: str,
    ) -> None:
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._sensor_info = sensor_info
        self._base_slug = base_slug

    @property
    def _sensor_data(self) -> dict | None:
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key)
        if not info:
            return None
        return info.get("data")

    @property
    def available(self) -> bool:
        return self._sensor_data is not None

    @property
    def device_info(self) -> dict[str, Any]:
        """Represent each subDevice as its own HA device."""
        from .const import DOMAIN
        hid = self._sensor_info["hid"]
        mid = self._sensor_info["mid"]
        addr = self._sensor_info["addr"]
        sub_name = self._sensor_info.get("sub_name") or f"Sensor {addr}"
        model = self._sensor_info.get("model") or "Unknown"
        return {
            "identifiers": {(DOMAIN, f"{hid}_{mid}_{addr}")},
            "name": sub_name,
            "manufacturer": "HomGar",
            "model": model,
        }


class HomGarDeviceIDSensor(HomGarDiagnosticSensorBase):
    """Device ID diagnostic sensor."""

    _attr_icon = "mdi:identifier"

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        sub_name = sensor_info.get("sub_name") or "Sensor"
        self._attr_unique_id = f"homgar_{base_slug}_device_id"
        self._attr_name = f"{sub_name} Device ID"

    @property
    def native_value(self) -> str | int | None:
        # Try to get device ID from sensor info first
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key)
        if info:
            # Log available fields for debugging
            import logging
            _LOGGER = logging.getLogger(__name__)
            _LOGGER.debug("Available fields for %s: %s", self._sensor_key, list(info.keys()))
            
            # Check for various possible device ID fields
            device_id_fields = [
                "device_id", "deviceId", "id", "deviceID",
                "sub_device_id", "subDeviceId", "subDeviceID",
                "device_sn", "deviceSN", "serial_number", "serialNumber",
                "addr", "address", "mac", "mac_address"
            ]
            
            for field in device_id_fields:
                device_id = info.get(field)
                if device_id:
                    _LOGGER.debug("Found device ID field %s: %s", field, device_id)
                    # Check if this looks like the RainPoint device ID (10 digits starting with 1)
                    if isinstance(device_id, (int, str)) and str(device_id).isdigit() and len(str(device_id)) >= 9:
                        return device_id
            
            # Check if device ID is in the decoded data
            decoded_data = info.get("data", {})
            if decoded_data:
                _LOGGER.debug("Checking decoded data: %s", list(decoded_data.keys()))
                # Look for device ID in decoded data
                for field in device_id_fields:
                    device_id = decoded_data.get(field)
                    if device_id:
                        _LOGGER.debug("Found device ID in decoded data %s: %s", field, device_id)
                        if isinstance(device_id, (int, str)) and str(device_id).isdigit() and len(str(device_id)) >= 9:
                            return device_id
                
                # Check raw payload for device ID pattern
                raw_payload = decoded_data.get("raw_value")
                if raw_payload and isinstance(raw_payload, str):
                    # Look for 10-digit patterns in raw payload
                    import re
                    matches = re.findall(r'\b\d{9,}\b', raw_payload)
                    if matches:
                        _LOGGER.debug("Found potential device IDs in raw payload: %s", matches)
                        # Return the first match that looks like a device ID
                        for match in matches:
                            if match.startswith('1'):  # RainPoint IDs seem to start with 1
                                return int(match)
            
            # If no proper device ID found, log what we have
            _LOGGER.debug("No device ID found for %s, available info: %s", self._sensor_key, info)
            return None
        return None


class HomGarRSSISensor(HomGarDiagnosticSensorBase):
    """RSSI diagnostic sensor."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:wifi"

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        sub_name = sensor_info.get("sub_name") or "Sensor"
        self._attr_unique_id = f"homgar_{base_slug}_rssi"
        self._attr_name = f"{sub_name} Signal Strength"

    @property
    def native_value(self) -> int | None:
        data = self._sensor_data
        if data:
            return data.get("rssi_dbm")
        return None


class HomGarBatterySensor(HomGarDiagnosticSensorBase):
    """Battery diagnostic sensor."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery"

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        sub_name = sensor_info.get("sub_name") or "Sensor"
        self._attr_unique_id = f"homgar_{base_slug}_battery"
        self._attr_name = f"{sub_name} Battery"

    @property
    def native_value(self) -> int | None:
        data = self._sensor_data
        if data:
            return data.get("battery_percent")
        return None


class HomGarFirmwareVersionSensor(HomGarDiagnosticSensorBase):
    """Firmware version diagnostic sensor."""

    _attr_icon = "mdi:chip"

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        sub_name = sensor_info.get("sub_name") or "Sensor"
        self._attr_unique_id = f"homgar_{base_slug}_firmware_version"
        self._attr_name = f"{sub_name} Firmware Version"

    @property
    def native_value(self) -> str | None:
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key)
        if info:
            return info.get("firmware_version")
        return None


class HomGarLastUpdatedSensor(HomGarDiagnosticSensorBase):
    """Last updated timestamp diagnostic sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        sub_name = sensor_info.get("sub_name") or "Sensor"
        self._attr_unique_id = f"homgar_{base_slug}_last_updated"
        self._attr_name = f"{sub_name} Last Updated"

    @property
    def native_value(self) -> datetime | None:
        data = self._sensor_data
        if data and "device_timestamp" in data:
            try:
                # Parse ISO format timestamp
                return datetime.fromisoformat(data["device_timestamp"].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
        return None
