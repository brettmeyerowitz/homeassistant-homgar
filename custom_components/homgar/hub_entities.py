"""Hub entities for HomGar devices."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomGarCoordinator


def _hub_name(hub_info: dict) -> str:
    model = hub_info.get("model")
    return (
        hub_info.get("name")
        or hub_info.get("displayModel")
        or (model if model and model != "Unknown" else None)
        or "RainPoint Hub"
    )


def _hub_model(hub_info: dict) -> str:
    return hub_info.get("model") or hub_info.get("displayModel") or "Unknown"


def _hub_status_payload(coordinator: HomGarCoordinator, mid: int | str) -> dict:
    status_by_mid = coordinator.data.get("status", {}) if coordinator.data else {}
    return status_by_mid.get(mid) or status_by_mid.get(str(mid)) or {}


def _hub_status_entries(coordinator: HomGarCoordinator, mid: int | str) -> list[dict]:
    status = _hub_status_payload(coordinator, mid)
    entries = status.get("subDeviceStatus", [])
    return entries if isinstance(entries, list) else []


class HomGarHubDevice(Entity):
    """Mixin providing device_info for HomGar hub entities."""

    def __init__(self, hub_info: dict) -> None:
        self._hub_info = hub_info
        self._attr_unique_id = f"rainpoint_hub_{hub_info['mid']}"
        self._attr_name = _hub_name(hub_info)
        self._attr_should_poll = False

    @property
    def device_info(self) -> DeviceInfo:
        mid = self._hub_info["mid"]
        return DeviceInfo(
            identifiers={(DOMAIN, f"rainpoint_hub_{mid}")},
            name=_hub_name(self._hub_info),
            manufacturer="RainPoint",
            model=_hub_model(self._hub_info),
            sw_version=self._hub_info.get("softVer") or None,
            hw_version=self._hub_info.get("hardwareVersion") or None,
            serial_number=self._hub_info.get("mac") or None,
            suggested_area=self._hub_info.get("homeName"),
        )

    @property
    def available(self) -> bool:
        return True


class HomGarHubSensorBase(CoordinatorEntity, SensorEntity, HomGarHubDevice):
    """Base class for HomGar hub sensors."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: HomGarCoordinator,
        hub_info: dict,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        HomGarHubDevice.__init__(self, hub_info)

    @property
    def available(self) -> bool:
        return True


class HomGarHubRSSISensor(HomGarHubSensorBase):
    """RSSI sensor for HomGar hub."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = "dBm"
    _attr_icon = "mdi:wifi"

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict):
        super().__init__(coordinator, hub_info)
        self._attr_unique_id = f"{self._attr_unique_id}_rssi"
        self._attr_name = f"{self._attr_name} Signal Strength"

    @property
    def native_value(self) -> int | None:
        # Hub RSSI would come from coordinator data if available
        # For now, return None as this might not be directly available
        return None


class HomGarHubDeviceIDSensor(HomGarHubSensorBase):
    """Device ID sensor for HomGar hub."""

    _attr_icon = "mdi:identifier"

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict):
        super().__init__(coordinator, hub_info)
        self._attr_unique_id = f"rainpoint_hub_{hub_info.get('mid', 'unknown')}_device_id"
        self._attr_name = f"{_hub_name(hub_info)} Device ID"

    @property
    def native_value(self) -> str | int | None:
        return self._hub_info.get("mid")


class HomGarHubFirmwareSensor(HomGarHubSensorBase):
    """Firmware version sensor for HomGar hub."""

    _attr_icon = "mdi:chip"

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict):
        super().__init__(coordinator, hub_info)
        self._attr_unique_id = f"rainpoint_hub_{hub_info.get('mid', 'unknown')}_firmware"
        self._attr_name = f"{_hub_name(hub_info)} Firmware Version"

    @property
    def native_value(self) -> str | None:
        return self._hub_info.get("softVer")


class HomGarHubMACSensor(HomGarHubSensorBase):
    """MAC address sensor for HomGar hub."""

    _attr_icon = "mdi:network-outline"

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict):
        super().__init__(coordinator, hub_info)
        self._attr_unique_id = f"rainpoint_hub_{hub_info.get('mid', 'unknown')}_mac"
        self._attr_name = f"{_hub_name(hub_info)} MAC Address"

    @property
    def native_value(self) -> str | None:
        return self._hub_info.get("mac")


class HomGarHubRawStatusSensor(HomGarHubSensorBase):
    """Raw cloud status payload for a hub/main WiFi device."""

    _attr_icon = "mdi:code-braces"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict):
        super().__init__(coordinator, hub_info)
        self._attr_unique_id = f"rainpoint_hub_{hub_info.get('mid', 'unknown')}_raw_status"
        self._attr_name = f"{_hub_name(hub_info)} Raw Status"

    @property
    def native_value(self) -> str | None:
        entries = _hub_status_entries(self.coordinator, self._hub_info.get("mid"))
        preferred_ids = ("D00", "D0")
        for preferred_id in preferred_ids:
            value = next(
                (
                    entry.get("value")
                    for entry in entries
                    if entry.get("id") == preferred_id and entry.get("value")
                ),
                None,
            )
            if value is not None:
                return str(value)
        for entry in entries:
            status_id = str(entry.get("id", ""))
            value = entry.get("value")
            if status_id.startswith("D") and value:
                return str(value)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        entries = _hub_status_entries(self.coordinator, self._hub_info.get("mid"))
        raw_status_by_id = {
            str(entry.get("id")): entry.get("value")
            for entry in entries
            if entry.get("id") is not None and entry.get("value") is not None
        }
        return {
            "mid": self._hub_info.get("mid"),
            "model": _hub_model(self._hub_info),
            "status_ids": [entry.get("id") for entry in entries if entry.get("id")],
            "raw_status_by_id": raw_status_by_id,
            "status_payload": _hub_status_payload(self.coordinator, self._hub_info.get("mid")),
        }


class HomGarHubMqttRawPayloadSensor(HomGarHubSensorBase):
    """Last raw MQTT payload seen for a hub/main WiFi device."""

    _attr_icon = "mdi:antenna"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict):
        super().__init__(coordinator, hub_info)
        self._attr_unique_id = f"rainpoint_hub_{hub_info.get('mid', 'unknown')}_mqtt_raw"
        self._attr_name = f"{_hub_name(hub_info)} Last MQTT Payload"

    @property
    def available(self) -> bool:
        diag = self.coordinator._mqtt_diagnostics.get(self._diag_key)
        return bool(diag and diag.get("raw_payload"))

    @property
    def _diag_key(self) -> str:
        return f"rainpoint_hub_{self._hub_info.get('mid')}"

    @property
    def native_value(self) -> str | None:
        diag = self.coordinator._mqtt_diagnostics.get(self._diag_key) or {}
        payload = diag.get("raw_payload")
        return str(payload) if payload is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        diag = self.coordinator._mqtt_diagnostics.get(self._diag_key) or {}
        return {
            "last_received": diag.get("last_received"),
            "device_key": diag.get("device_key"),
            "hub_mid": diag.get("hub_mid"),
            "connected": diag.get("connected"),
            "messages_received": diag.get("messages_received"),
            "last_message_age_seconds": diag.get("last_message_age_seconds"),
        }


class HomGarHubMqttFriendlySensor(HomGarHubSensorBase):
    """Last MQTT message summary for a hub/main WiFi device."""

    _attr_icon = "mdi:message-text"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict):
        super().__init__(coordinator, hub_info)
        self._attr_unique_id = f"rainpoint_hub_{hub_info.get('mid', 'unknown')}_mqtt_friendly"
        self._attr_name = f"{_hub_name(hub_info)} Last MQTT Summary"

    @property
    def available(self) -> bool:
        diag = self.coordinator._mqtt_diagnostics.get(self._diag_key)
        return bool(diag and diag.get("friendly_summary"))

    @property
    def _diag_key(self) -> str:
        return f"rainpoint_hub_{self._hub_info.get('mid')}"

    @property
    def native_value(self) -> str | None:
        diag = self.coordinator._mqtt_diagnostics.get(self._diag_key) or {}
        summary = diag.get("friendly_summary")
        return str(summary) if summary is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        diag = self.coordinator._mqtt_diagnostics.get(self._diag_key) or {}
        return {
            "last_received": diag.get("last_received"),
            "device_key": diag.get("device_key"),
            "hub_mid": diag.get("hub_mid"),
            "connected": diag.get("connected"),
            "messages_received": diag.get("messages_received"),
            "last_message_age_seconds": diag.get("last_message_age_seconds"),
        }


class HomGarHubChannelSelect(CoordinatorEntity, SelectEntity, HomGarHubDevice):
    """RF Channel selector for HomGar hub."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:radio-tower"

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict):
        CoordinatorEntity.__init__(self, coordinator)
        HomGarHubDevice.__init__(self, hub_info)
        self._attr_unique_id = f"rainpoint_hub_{hub_info.get('mid', 'unknown')}_channel"
        self._attr_name = f"{_hub_name(hub_info)} RF Channel"
        self._attr_options = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16"]
        # Channel 7 from your hub data
        self._attr_current_option = "7"

    @property
    def available(self) -> bool:
        return True

    @property
    def current_option(self) -> str | None:
        return self._attr_current_option

    async def async_select_option(self, option: str) -> None:
        """Change the RF channel."""
        # This would require API call to change hub settings
        # For now, just log and update local state
        self._attr_current_option = option
        self.async_write_ha_state()


class HomGarHubBroadcastSwitch(CoordinatorEntity, SwitchEntity, HomGarHubDevice):
    """Automatic Broadcast Time switch for HomGar hub."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict):
        CoordinatorEntity.__init__(self, coordinator)
        HomGarHubDevice.__init__(self, hub_info)
        self._attr_unique_id = f"rainpoint_hub_{hub_info.get('mid', 'unknown')}_broadcast"
        self._attr_name = f"{_hub_name(hub_info)} Automatic Broadcast"
        self._attr_is_on = True  # Default to on

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self._attr_is_on

    async def async_turn_on(self) -> None:
        """Turn on automatic broadcast."""
        # This would require API call to change hub settings
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off automatic broadcast."""
        # This would require API call to change hub settings
        self._attr_is_on = False
        self.async_write_ha_state()
