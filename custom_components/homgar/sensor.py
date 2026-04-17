from __future__ import annotations

import logging
import re
from typing import Any

from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_GROUP_MULTI_ZONE_DEVICES,
    controller_device_identifier,
    format_port_device_name,
    format_port_entity_name,
    zone_device_identifier,
)
from .coordinator import HomGarCoordinator
from .sensor_defs import FIELD_SENSOR_MAP, sensor_fields_for_data
from .decoder import get_valve_ports
from .diagnostic_sensors import (
    HomGarFirmwareVersionSensor,
    HomGarMqttRawPayloadSensor,
    HomGarMqttFriendlySensor,
)
from .hub_entities import (
    HomGarHubDeviceIDSensor,
    HomGarHubFirmwareSensor,
    HomGarHubMACSensor,
    HomGarHubChannelSelect,
    HomGarHubBroadcastSwitch,
)

_LOGGER = logging.getLogger(__name__)


_OPTIONAL_VALVE_PORT_SENSOR_FIELDS = (
    "event_time",
    "event_time2",
    "irrigation_end_time",
    "cycle_type",
)

_LOCAL_TLV_TIMESTAMP_FIELDS = {"event_time", "event_time2", "irrigation_end_time"}
_MODEL_SENSOR_LABEL_OVERRIDES: dict[str, dict[str, str]] = {
    "HCS044FRF": {
        "event_time": "Rain Event Time",
    },
}


def _filtered_sensor_fields(model: str | None, data: dict) -> set[str]:
    fields = set(sensor_fields_for_data(data))
    return fields


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HomGarCoordinator = entry_data["coordinator"]

    sensors_cfg = coordinator.data.get("sensors", {})
    hubs_cfg = coordinator.data.get("hubs", [])

    entities: list[HomGarSensorBase] = []

    # Create hub entities first
    if isinstance(hubs_cfg, list):
        # Convert list to dict for easier processing
        hubs_dict = {str(hub.get("mid", i)): hub for i, hub in enumerate(hubs_cfg)}
    else:
        hubs_dict = hubs_cfg
    
    for hub_key, hub_info in hubs_dict.items():
        hub_name = hub_info.get("name", "HomGar Hub")
        hub_slug = _slugify(f"hub_{hub_name}")
        
        # Add hub sensors
        entities.append(HomGarHubDeviceIDSensor(coordinator, hub_info))
        entities.append(HomGarHubFirmwareSensor(coordinator, hub_info))
        entities.append(HomGarHubMACSensor(coordinator, hub_info))
        entities.append(HomGarHubChannelSelect(coordinator, hub_info))
        entities.append(HomGarHubBroadcastSwitch(coordinator, hub_info))

    # Create sensor entities for sub-devices
    for key, info in sensors_cfg.items():
        model = info.get("model")
        base_slug = key
        data = info.get("data") or {}
        _LOGGER.debug("Creating sensor entities: key=%s model=%s", key, model)

        if data.get("type") == "unknown":
            entities.append(HomGarUnknownSensor(coordinator, key, info, base_slug))
        else:
            port_number = data.get("port_number", 1)
            if port_number and port_number > 1:
                # Multi-port device: create per-port sensors + shared top-level fields
                for port in range(1, port_number + 1):
                    port_data = data.get(f"port_{port}", {})
                    port_fields = _filtered_sensor_fields(model, port_data)
                    if model and get_valve_ports(model):
                        port_fields.update(_OPTIONAL_VALVE_PORT_SENSOR_FIELDS)
                    for field in sorted(port_fields):
                        entities.append(HomGarGenericSensor(coordinator, key, info, field, port=port))
                # Shared top-level diagnostic fields (battery, rssi)
                for field in sensor_fields_for_data(data):
                    if field not in (f for pd in [data.get(f"port_{p}", {}) for p in range(1, port_number + 1)] for f in pd):
                        entities.append(HomGarGenericSensor(coordinator, key, info, field))
            else:
                # Single-port device
                fields = _filtered_sensor_fields(model, data)
                if model and get_valve_ports(model):
                    fields.update(_OPTIONAL_VALVE_PORT_SENSOR_FIELDS)
                for field in sorted(fields):
                    entities.append(HomGarGenericSensor(coordinator, key, info, field))

        # Diagnostic sensors for all sub-devices
        entities.append(HomGarFirmwareVersionSensor(coordinator, key, info, base_slug))

        # Raw payload sensor (disabled by default)
        entities.append(HomGarRawPayloadSensor(coordinator, key, info, base_slug))

        # MQTT diagnostic sensors (disabled by default)
        entities.append(HomGarMqttRawPayloadSensor(coordinator, key, info, base_slug))
        entities.append(HomGarMqttFriendlySensor(coordinator, key, info, base_slug))

    if entities:
        async_add_entities(entities)


class HomGarSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for HomGar sensors."""

    _attr_should_poll = False

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
        """Represent each subDevice as its own HA device, child of hub."""
        from .const import DOMAIN
        hid = self._sensor_info["hid"]
        mid = self._sensor_info["mid"]
        addr = self._sensor_info["addr"]
        sub_name = self._sensor_info.get("sub_name") or f"Sensor {addr}"
        model = self._sensor_info.get("model") or "Unknown"
        parent_ident = controller_device_identifier(self._sensor_info)
        port = self._device_port()
        group_multi_zone = (
            port is not None
            and self.coordinator._entry.options.get(CONF_GROUP_MULTI_ZONE_DEVICES, False)
            and len(get_valve_ports(model)) > 1
        )

        if group_multi_zone:
            return {
                "identifiers": {(DOMAIN, zone_device_identifier(mid, addr, port))},
                "name": format_port_device_name(sub_name, self._sensor_info, port),
                "manufacturer": "RainPoint",
                "model": model,
                "suggested_area": self._sensor_info.get("home_name"),
                "via_device": (DOMAIN, parent_ident),
            }
        if self._sensor_info.get("type_flag") == 1:
            return {
                "identifiers": {(DOMAIN, f"rainpoint_hub_{mid}")},
                "name": f"{sub_name}",
                "manufacturer": "RainPoint",
                "model": model,
                "suggested_area": self._sensor_info.get("home_name"),
            }
        return {
            "identifiers": {(DOMAIN, f"{mid}_{addr}")},
            "name": f"{sub_name}",
            "manufacturer": "RainPoint",
            "model": model,
            "suggested_area": self._sensor_info.get("home_name"),
            "via_device": (DOMAIN, f"rainpoint_hub_{mid}"),
        }

    def _device_port(self) -> int | None:
        """Return the port number that owns this entity, if any."""
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._sensor_data or {}
        attrs: dict[str, Any] = {}
        if "rssi_dbm" in data:
            attrs["rssi_dbm"] = data["rssi_dbm"]
        if "battery_percent" in data:
            attrs["battery_percent"] = data["battery_percent"]
        elif "battery_status_code" in data:
            attrs["battery_status_code"] = data["battery_status_code"]
        if "battery_status" in data:
            attrs["battery_status"] = data["battery_status"]

        # Add firmware version from sensor info
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key) or {}
        firmware_version = info.get("firmware_version")
        if firmware_version:
            attrs["firmware_version"] = firmware_version

        # Add device timestamp from decoded data
        if "device_timestamp" in data:
            attrs["device_timestamp"] = data["device_timestamp"]
            attrs["timestamp_method"] = data.get("timestamp_method")
            attrs["timestamp_source"] = data.get("timestamp_source", "server")
        elif "server_timestamp" in data:
            attrs["device_timestamp"] = data["server_timestamp"]
            attrs["timestamp_source"] = data.get("timestamp_source", "server")
        else:
            _LOGGER.debug("No timestamp found in sensor data: %s", data)
        
        # Legacy timestamp from raw_status (fallback)
        raw_status = info.get("raw_status") or {}
        ts = raw_status.get("time")
        if ts:
            try:
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                attrs["last_updated"] = dt.isoformat()
            except Exception:  # noqa: BLE001
                # If anything goes wrong, we simply omit last_updated
                pass

        _LOGGER.debug("Sensor %s attributes: %s", self._sensor_key, attrs)
        return attrs


class HomGarGenericSensor(HomGarSensorBase):
    """Generic field-driven sensor — reads one field from decoded device data."""

    def __init__(
        self,
        coordinator: HomGarCoordinator,
        sensor_key: str,
        sensor_info: dict,
        field_name: str,
        port: int | None = None,
    ) -> None:
        base_slug = sensor_key
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._field_name = field_name
        self._port = port

        sdef = FIELD_SENSOR_MAP.get(field_name)
        if sdef:
            if sdef.device_class:
                self._attr_device_class = sdef.device_class
            if sdef.unit:
                self._attr_native_unit_of_measurement = sdef.unit
            if sdef.state_class:
                self._attr_state_class = sdef.state_class
            if sdef.entity_category:
                self._attr_entity_category = sdef.entity_category
            if sdef.icon:
                self._attr_icon = sdef.icon

        sub_name = sensor_info.get("sub_name") or "Sensor"
        label = (sdef.name if sdef and sdef.name else field_name.replace("_", " ").title())
        model = (sensor_info.get("model") or "").upper()
        if model:
            label = _MODEL_SENSOR_LABEL_OVERRIDES.get(model, {}).get(field_name, label)
        if port is not None:
            uid_suffix = f"{field_name}_port{port}"
            self._attr_name = format_port_entity_name(
                sub_name,
                sensor_info,
                port,
                label,
                use_device_prefix=(
                    self.coordinator._entry.options.get(CONF_GROUP_MULTI_ZONE_DEVICES, False)
                    and len(get_valve_ports(sensor_info.get("model"))) > 1
                ),
            )
        else:
            uid_suffix = field_name
            self._attr_name = f"{sub_name} {label}"
        self._attr_unique_id = f"rainpoint_{base_slug}_{uid_suffix}"

    @property
    def _source_data(self) -> dict | None:
        data = self._sensor_data
        if data is None:
            return None
        if self._port is not None:
            return data.get(f"port_{self._port}")
        return data

    def _device_port(self) -> int | None:
        return self._port

    @property
    def native_value(self):
        src = self._source_data
        value = src.get(self._field_name) if src else None
        if (
            value is None
            and self._field_name == "last_water_volume"
            and src
            and src.get("is_watering") is True
        ):
            # Some valve payloads omit an explicit last-session volume while a
            # run is active. Prefer a stable zero value over unavailable.
            value = 0.0
        if value is not None and getattr(self, "_attr_device_class", None) == SensorDeviceClass.TIMESTAMP and isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
                raw_status = self._sensor_info.get("raw_status") or {}
                raw_payload = raw_status.get("value")
                if (
                    self._field_name in _LOCAL_TLV_TIMESTAMP_FIELDS
                    and isinstance(raw_payload, str)
                    and "#" in raw_payload
                    and value.tzinfo is not None
                ):
                    local_tz = dt_util.get_time_zone(self.coordinator.hass.config.time_zone)
                    if local_tz is not None:
                        # RainPoint TLV event times are packed as local wall clock values.
                        # Reinterpret the decoded wall time in HA's configured timezone
                        # before exposing it as an absolute timestamp.
                        value = value.replace(tzinfo=None).replace(tzinfo=local_tz).astimezone(timezone.utc)
            except (ValueError, TypeError):
                value = None
        _LOGGER.debug("native_value for %s field=%s port=%s: %s", self._sensor_key, self._field_name, self._port, value)
        return value


class HomGarUnknownSensor(HomGarSensorBase):
    """Diagnostic sensor for unknown/unsupported models.
    
    This sensor surfaces raw payload data in Home Assistant so users can
    easily copy it when reporting issues for new sensor support.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:help-circle-outline"

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        model = sensor_info.get("model", "unknown")
        self._attr_unique_id = f"rainpoint_{base_slug}_unknown_{model}"
        sub_name = sensor_info.get("sub_name") or "Sensor"
        self._attr_name = f"{sub_name} Unsupported ({model})"

    @property
    def native_value(self) -> str:
        """Return the model name as the state."""
        data = self._sensor_data
        if data:
            return f"Unsupported: {data.get('model', 'unknown')}"
        return "No data"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Include raw payload and instructions for reporting."""
        attrs = super().extra_state_attributes
        data = self._sensor_data or {}
        
        attrs["model"] = data.get("model")
        attrs["raw_payload"] = data.get("raw_value")
        attrs["report_url"] = "https://github.com/brettmeyerowitz/homeassistant-homgar/issues"
        attrs["instructions"] = (
            "This sensor model is not yet supported. "
            "Please open a GitHub issue with the model and raw_payload values above."
        )
        
        return attrs


class HomGarRawPayloadSensor(HomGarSensorBase):
    """Raw hex payload sensor (diagnostic, disabled by default)."""
    
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:code-braces"
    _attr_entity_registry_enabled_default = False  # Disabled by default
    
    def __init__(
        self,
        coordinator: HomGarCoordinator,
        sensor_key: str,
        sensor_info: dict,
        base_slug: str,
    ) -> None:
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        sub_name = sensor_info.get("sub_name") or "Sensor"
        self._attr_unique_id = f"rainpoint_{base_slug}_raw_payload"
        self._attr_name = f"{sub_name} Raw Payload"
    
    @property
    def native_value(self) -> str | None:
        """Return the raw hex payload string."""
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key) or {}
        raw_status = info.get("raw_status") or {}
        value = raw_status.get("value")
        _LOGGER.debug("native_value for %s (raw_payload): %s", self._sensor_key, value)
        return value
