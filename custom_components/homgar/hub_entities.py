"""Hub entities for HomGar devices."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomGarCoordinator
from .device import HomGarHubDevice


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
        self._attr_unique_id = f"homgar_hub_{hub_info.get('hid', 'unknown')}_device_id"
        self._attr_name = f"{hub_info.get('name', 'HomGar Hub')} Device ID"

    @property
    def native_value(self) -> str | int | None:
        return self._hub_info.get("hid")


class HomGarHubFirmwareSensor(HomGarHubSensorBase):
    """Firmware version sensor for HomGar hub."""

    _attr_icon = "mdi:chip"

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict):
        super().__init__(coordinator, hub_info)
        self._attr_unique_id = f"homgar_hub_{hub_info.get('hid', 'unknown')}_firmware"
        self._attr_name = f"{hub_info.get('name', 'HomGar Hub')} Firmware Version"

    @property
    def native_value(self) -> str | None:
        return self._hub_info.get("softVer")


class HomGarHubMACSensor(HomGarHubSensorBase):
    """MAC address sensor for HomGar hub."""

    _attr_icon = "mdi:network-outline"

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict):
        super().__init__(coordinator, hub_info)
        self._attr_unique_id = f"homgar_hub_{hub_info.get('hid', 'unknown')}_mac"
        self._attr_name = f"{hub_info.get('name', 'HomGar Hub')} MAC Address"

    @property
    def native_value(self) -> str | None:
        return self._hub_info.get("mac")


class HomGarHubChannelSelect(CoordinatorEntity, SelectEntity, HomGarHubDevice):
    """RF Channel selector for HomGar hub."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:radio-tower"

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict):
        CoordinatorEntity.__init__(self, coordinator)
        HomGarHubDevice.__init__(self, hub_info)
        self._attr_unique_id = f"homgar_hub_{hub_info.get('hid', 'unknown')}_channel"
        self._attr_name = f"{hub_info.get('name', 'HomGar Hub')} RF Channel"
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
        self._attr_unique_id = f"homgar_hub_{hub_info.get('hid', 'unknown')}_broadcast"
        self._attr_name = f"{hub_info.get('name', 'HomGar Hub')} Automatic Broadcast"
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
