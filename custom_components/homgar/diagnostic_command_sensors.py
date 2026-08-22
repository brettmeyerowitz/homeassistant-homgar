"""Command-failure diagnostic sensors (issue #82).

Two local-only DIAGNOSTIC sensors on the Hub device exposing the client's
write-failure telemetry, so a valve command that never reached the cloud is
visible instead of silent.

Why sensors and not just a notification: a persistent notification is a banner
the user has to dismiss in the UI, and it decides *for* them how they want to
hear about it. Exposing the failure as state lets people build their own
automation off it — phone push, Telegram, a red badge on a dashboard, or
nothing at all. The notification (wired in __init__.py) is the loud channel for
the definitive failure; these sensors are the quiet, automatable one.

Writes only. A failed poll self-heals on the next coordinator cycle, so counting
it here would bury the signal these sensors exist to carry. No network, no PII.
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


class _HomGarCommandSensorBase(CoordinatorEntity, SensorEntity):
    """Base for the account-level command diagnostic sensors (one set per entry)."""

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


class HomGarCommandFailureCountSensor(_HomGarCommandSensorBase):
    """Control commands that failed outright since HA (re)started."""

    _attr_icon = "mdi:cloud-alert"
    _attr_name = "Failed commands"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, hub_info, entry_id):
        super().__init__(coordinator, hub_info, entry_id)
        self._attr_unique_id = f"{entry_id}_command_failure_count"

    @property
    def native_value(self) -> int:
        return self._client.write_failure_count


class HomGarLastCommandFailureSensor(_HomGarCommandSensorBase):
    """When the most recent control command gave up, and what it was."""

    _attr_icon = "mdi:valve-closed"
    _attr_name = "Last failed command"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, hub_info, entry_id):
        super().__init__(coordinator, hub_info, entry_id)
        self._attr_unique_id = f"{entry_id}_last_command_failure"

    @property
    def native_value(self) -> datetime | None:
        return self._client.last_write_failure_at

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "command": self._client.last_write_failure_what,
            "last_error": self._client.last_write_failure_error,
        }


def build_command_diagnostic_sensors(
    coordinator: HomGarCoordinator, hub_info: dict, entry_id: str
) -> list[_HomGarCommandSensorBase]:
    """Build the one-per-entry command-failure diagnostic sensor set."""
    return [
        HomGarCommandFailureCountSensor(coordinator, hub_info, entry_id),
        HomGarLastCommandFailureSensor(coordinator, hub_info, entry_id),
    ]
