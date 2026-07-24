"""Token re-auth diagnostic sensors (v3.0.41).

Three local-only DIAGNOSTIC sensors on the Hub device that expose the client's
session token re-auth telemetry, so a token being rejected repeatedly (e.g. a
concurrent-session war) is visible from the HA history graph. No network, no
PII. See docs/superpowers/specs/2026-07-24-token-reauth-diagnostic-sensors-design.md.
"""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomGarCoordinator


class _HomGarTokenSensorBase(CoordinatorEntity, SensorEntity):
    """Base for the account-level token diagnostic sensors (one set per entry)."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = True
    _attr_has_entity_name = True

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict, entry_id: str) -> None:
        super().__init__(coordinator)
        self._hub_info = hub_info
        self._entry_id = entry_id

    @property
    def _client(self):
        return self.coordinator._client

    @property
    def available(self) -> bool:
        return self.coordinator._client is not None

    @property
    def device_info(self) -> DeviceInfo:
        mid = self._hub_info["mid"]
        return DeviceInfo(identifiers={(DOMAIN, f"rainpoint_hub_{mid}")})


class HomGarTokenReauthCountSensor(_HomGarTokenSensorBase):
    """Number of token re-authentications since HA (re)started."""

    _attr_icon = "mdi:counter"
    _attr_name = "Token re-auth count"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, hub_info, entry_id):
        super().__init__(coordinator, hub_info, entry_id)
        self._attr_unique_id = f"{entry_id}_token_reauth_count"

    @property
    def native_value(self) -> int:
        return self._client.reauth_count


class HomGarLastTokenReauthSensor(_HomGarTokenSensorBase):
    """Timestamp of the most recent token re-authentication."""

    _attr_icon = "mdi:key-alert"
    _attr_name = "Last token re-auth"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, hub_info, entry_id):
        super().__init__(coordinator, hub_info, entry_id)
        self._attr_unique_id = f"{entry_id}_last_token_reauth"

    @property
    def native_value(self) -> datetime | None:
        return self._client.last_reauth_at

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "trigger_endpoint": self._client.last_reauth_trigger,
            "last_error_code": self._client.last_reauth_code,
        }


class HomGarTokenExpiresAtSensor(_HomGarTokenSensorBase):
    """When the current token expires (far future => not natural expiry)."""

    _attr_icon = "mdi:clock-end"
    _attr_name = "Token expires at"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, hub_info, entry_id):
        super().__init__(coordinator, hub_info, entry_id)
        self._attr_unique_id = f"{entry_id}_token_expires_at"

    @property
    def native_value(self) -> datetime | None:
        return self._client.token_expires_at


def build_token_diagnostic_sensors(
    coordinator: HomGarCoordinator, hub_info: dict, entry_id: str
) -> list[_HomGarTokenSensorBase]:
    """Build the one-per-entry token diagnostic sensor set."""
    return [
        HomGarTokenReauthCountSensor(coordinator, hub_info, entry_id),
        HomGarLastTokenReauthSensor(coordinator, hub_info, entry_id),
        HomGarTokenExpiresAtSensor(coordinator, hub_info, entry_id),
    ]
