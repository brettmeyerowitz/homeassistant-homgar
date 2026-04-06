"""MQTT diagnostic sensors for HomGar valve controllers.

Provides connectivity status and message statistics for MQTT-enabled devices.
"""

import logging
import time
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class HomGarMQTTDiagnosticsSensor(SensorEntity, CoordinatorEntity):
    """Base class for MQTT diagnostic sensors."""

    def __init__(self, coordinator, sensor_key: str, device_info: dict, field_name: str):
        """Initialize MQTT diagnostic sensor."""
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._device_info = device_info
        self._field_name = field_name
        self._attr_unique_id = f"homgar_{sensor_key}_mqtt_{field_name}"
        self._attr_name = f"{device_info.get('sub_name', 'MQTT')} {field_name.replace('_', ' ').title()}"
        self._attr_entity_registry_enabled_default = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._sensor_key)},
            "name": self._device_info.get("sub_name", "MQTT Diagnostics"),
            "manufacturer": "HomGar/RainPoint",
            "model": self._device_info.get("model", "Unknown"),
            "via_device": (DOMAIN, self._device_info.get("hid")),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.data is not None

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        data = self.coordinator.data
        if not data:
            return None

        mqtt_diagnostics = data.get("mqtt_diagnostics", {}).get(self._sensor_key, {})
        return mqtt_diagnostics.get(self._field_name)


class HomGarMQTTConnectionSensor(HomGarMQTTDiagnosticsSensor):
    """Sensor for MQTT connection status."""

    def __init__(self, coordinator, sensor_key: str, device_info: dict):
        super().__init__(coordinator, sensor_key, device_info, "connected")

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return the device class."""
        return SensorDeviceClass.CONNECTIVITY

    @property
    def native_value(self):
        """Return connection status as boolean."""
        value = super().native_value
        return "connected" if value else "disconnected"

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        data = self.coordinator.data
        if not data:
            return {}

        mqtt_diagnostics = data.get("mqtt_diagnostics", {}).get(self._sensor_key, {})
        return {
            "connection_attempts": mqtt_diagnostics.get("connection_attempts", 0),
            "uptime_seconds": mqtt_diagnostics.get("uptime_seconds", 0),
            "mqtt_host": mqtt_diagnostics.get("mqtt_host"),
            "mqtt_port": mqtt_diagnostics.get("mqtt_port"),
        }


class HomGarMQTTMessagesReceivedSensor(HomGarMQTTDiagnosticsSensor):
    """Sensor for MQTT messages received count."""

    def __init__(self, coordinator, sensor_key: str, device_info: dict):
        super().__init__(coordinator, sensor_key, device_info, "messages_received")

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return the device class."""
        return SensorDeviceClass.TOTAL

    @property
    def state_class(self) -> SensorStateClass:
        """Return the state class."""
        return SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self):
        """Return messages received count."""
        value = super().native_value
        return value if value is not None else 0

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        data = self.coordinator.data
        if not data:
            return {}

        mqtt_diagnostics = data.get("mqtt_diagnostics", {}).get(self._sensor_key, {})
        last_message_age = mqtt_diagnostics.get("last_message_age_seconds")
        attrs = {}
        
        if last_message_age is not None:
            attrs["last_message_age_seconds"] = last_message_age
            attrs["last_message_time"] = mqtt_diagnostics.get("last_message_time")
        
        return attrs


class HomGarMQTTMessagesSentSensor(HomGarMQTTDiagnosticsSensor):
    """Sensor for MQTT messages sent count."""

    def __init__(self, coordinator, sensor_key: str, device_info: dict):
        super().__init__(coordinator, sensor_key, device_info, "messages_sent")

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return the device class."""
        return SensorDeviceClass.TOTAL

    @property
    def state_class(self) -> SensorStateClass:
        """Return the state class."""
        return SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self):
        """Return messages sent count."""
        value = super().native_value
        return value if value is not None else 0


class HomGarMQTTLastMessageSensor(HomGarMQTTDiagnosticsSensor):
    """Sensor for time since last MQTT message."""

    def __init__(self, coordinator, sensor_key: str, device_info: dict):
        super().__init__(coordinator, sensor_key, device_info, "last_message_age_seconds")

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def state_class(self) -> SensorStateClass:
        """Return the state class."""
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return UnitOfTime.SECONDS

    @property
    def native_value(self):
        """Return time since last message."""
        value = super().native_value
        return value if value is not None and value >= 0 else None

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        data = self.coordinator.data
        if not data:
            return {}

        mqtt_diagnostics = data.get("mqtt_diagnostics", {}).get(self._sensor_key, {})
        return {
            "last_message_time": mqtt_diagnostics.get("last_message_time"),
            "total_messages": mqtt_diagnostics.get("messages_received", 0),
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MQTT diagnostic sensors."""
    from .const import DOMAIN
    from .coordinator import HomGarCoordinator

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HomGarCoordinator = data["coordinator"]

    entities = []

    # Check if MQTT client is available and has diagnostics
    mqtt_client = getattr(coordinator, "_mqtt_client", None)
    if mqtt_client and hasattr(mqtt_client, "get_diagnostics"):
        # Create diagnostic sensors for each hub with MQTT
        hubs = coordinator.data.get("hubs", [])
        for hub in hubs:
            hub_key = f"{hub.get('hid')}_{hub.get('mid')}"
            
            # Only create if hub has MQTT credentials
            if hub.get("productKey") and hub.get("deviceName"):
                device_info = {
                    "hid": hub.get("hid"),
                    "mid": hub.get("mid"),
                    "sub_name": f"MQTT {hub.get('name', 'Hub')}",
                    "model": "MQTT Diagnostics",
                }

                entities.extend([
                    HomGarMQTTConnectionSensor(coordinator, hub_key, device_info),
                    HomGarMQTTMessagesReceivedSensor(coordinator, hub_key, device_info),
                    HomGarMQTTMessagesSentSensor(coordinator, hub_key, device_info),
                    HomGarMQTTLastMessageSensor(coordinator, hub_key, device_info),
                ])

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d MQTT diagnostic sensors", len(entities))
    else:
        _LOGGER.debug("No MQTT client available, skipping diagnostic sensors")
