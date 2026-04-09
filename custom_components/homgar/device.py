"""Device representation for HomGar hubs and sub-devices."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from .const import DOMAIN


class HomGarHubDevice(Entity):
    """Base class for HomGar hub devices."""

    def __init__(
        self,
        hub_info: dict,
    ) -> None:
        self._hub_info = hub_info
        self._attr_unique_id = f"rainpoint_hub_{hub_info['mid']}"
        self._attr_name = hub_info.get("name", "HomGar Hub")
        self._attr_should_poll = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this hub."""
        mid = self._hub_info['mid']
        return DeviceInfo(
            identifiers={(DOMAIN, f"rainpoint_hub_{mid}")},
            name=self._hub_info.get("name", "HomGar Hub"),
            manufacturer="RainPoint",
            model=self._hub_info.get("model", "Unknown"),
            sw_version=self._hub_info.get("softVer"),
            hw_version=self._hub_info.get("hardwareVersion"),
            serial_number=self._hub_info.get("mac"),
            suggested_area=self._hub_info.get("homeName"),
        )

    @property
    def available(self) -> bool:
        return True  # Hub is always available if config exists


class HomGarSubDevice(Entity):
    """Base class for HomGar sub-devices (sensors, valves, etc.)."""

    def __init__(
        self,
        hub_info: dict,
        sub_device_info: dict,
    ) -> None:
        self._hub_info = hub_info
        self._sub_device_info = sub_device_info

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this sub-device."""
        mid = self._sub_device_info['mid']
        addr = self._sub_device_info['addr']
        return DeviceInfo(
            identifiers={(DOMAIN, f"{mid}_{addr}")},
            name=self._sub_device_info.get("sub_name") or f"Device {addr}",
            manufacturer="RainPoint",
            model=self._sub_device_info.get("model", "Unknown"),
            sw_version=self._sub_device_info.get("softVer"),
            via_device=(DOMAIN, f"rainpoint_hub_{self._hub_info['mid']}"),
        )
