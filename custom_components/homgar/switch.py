from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_GROUP_MULTI_ZONE_DEVICES,
    DOMAIN,
    controller_device_identifier,
    format_port_device_name,
    format_port_entity_name,
    zone_device_identifier,
)
from .coordinator import HomGarCoordinator
from .decoder import get_switch_ports

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HomGarCoordinator = data["coordinator"]

    sensors_cfg = coordinator.data.get("sensors", {})
    entities: list[HomGarSocketSwitchEntity] = []

    for key, info in sensors_cfg.items():
        model = info.get("model")
        switch_ports = get_switch_ports(model) if model else []
        if not switch_ports:
            continue

        for port in switch_ports:
            entities.append(HomGarSocketSwitchEntity(coordinator, key, info, port))
            _LOGGER.debug(
                "Creating switch entity: key=%s port=%s model=%s",
                key, port, model,
            )

    if entities:
        async_add_entities(entities)


class HomGarSocketSwitchEntity(CoordinatorEntity, SwitchEntity):
    """Represents a single HomGar/RainPoint socket control."""

    _attr_should_poll = False

    def __init__(
        self,
        coordinator: HomGarCoordinator,
        sensor_key: str,
        sensor_info: dict,
        port_num: int,
    ) -> None:
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._sensor_info = sensor_info
        self._port_num = port_num

        mid = sensor_info["mid"]
        addr = sensor_info["addr"]
        sub_name = sensor_info.get("sub_name") or f"Socket {addr}"

        self._attr_unique_id = f"rainpoint_{mid}_{addr}_switch{port_num}"
        model = sensor_info.get("model") or ""
        switch_ports = get_switch_ports(model)
        grouped = (
            self.coordinator._entry.options.get(CONF_GROUP_MULTI_ZONE_DEVICES, False)
            and len(switch_ports) > 1
        )
        if len(switch_ports) <= 1:
            self._attr_name = sub_name
        else:
            self._attr_name = format_port_entity_name(
                sub_name,
                sensor_info,
                port_num,
                "Switch" if grouped else None,
                use_device_prefix=grouped,
            )

    @property
    def _port_data(self) -> dict | None:
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key)
        if not info:
            return None
        decoded = info.get("data")
        if not decoded:
            return None
        port = decoded.get(f"port_{self._port_num}")
        if port is not None:
            return port
        if self._port_num == 1 and "is_watering" in decoded:
            return decoded
        return None

    @property
    def available(self) -> bool:
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key)
        if not info:
            return False
        decoded = info.get("data")
        if not decoded:
            return False
        return decoded.get("hub_online", True)

    @property
    def is_on(self) -> bool | None:
        port = self._port_data
        if port is None:
            return None
        is_watering = port.get("is_watering")
        if is_watering is None:
            return None
        return bool(is_watering)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        port = self._port_data
        if port:
            attrs["work_mode"] = port.get("valve_state")

        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key) or {}
        firmware_version = info.get("firmware_version")
        if firmware_version:
            attrs["firmware_version"] = firmware_version

        data = info.get("data", {})
        if "device_timestamp" in data:
            attrs["device_timestamp"] = data["device_timestamp"]
            attrs["timestamp_method"] = data.get("timestamp_method")
            attrs["timestamp_source"] = data.get("timestamp_source", "server")
        elif "server_timestamp" in data:
            attrs["device_timestamp"] = data["server_timestamp"]
            attrs["timestamp_source"] = data.get("timestamp_source", "server")

        return attrs

    @property
    def device_info(self) -> dict[str, Any]:
        mid = self._sensor_info["mid"]
        addr = self._sensor_info["addr"]
        sub_name = self._sensor_info.get("sub_name") or f"Socket {addr}"
        model = self._sensor_info.get("model") or "Unknown"
        parent_ident = controller_device_identifier(self._sensor_info)
        if (
            self.coordinator._entry.options.get(CONF_GROUP_MULTI_ZONE_DEVICES, False)
            and len(get_switch_ports(model)) > 1
        ):
            return {
                "identifiers": {(DOMAIN, zone_device_identifier(mid, addr, self._port_num))},
                "name": format_port_device_name(sub_name, self._sensor_info, self._port_num),
                "manufacturer": "RainPoint",
                "model": model,
                "via_device": (DOMAIN, parent_ident),
            }
        if self._sensor_info.get("type_flag") == 1:
            return {
                "identifiers": {(DOMAIN, f"rainpoint_hub_{mid}")},
                "name": sub_name,
                "manufacturer": "RainPoint",
                "model": model,
            }
        return {
            "identifiers": {(DOMAIN, f"{mid}_{addr}")},
            "name": sub_name,
            "manufacturer": "RainPoint",
            "model": model,
        }

    def _apply_optimistic_port_update(self, is_on: bool) -> None:
        current = dict(self.coordinator.data)
        sensors = dict(current.get("sensors", {}))
        entry = sensors.get(self._sensor_key)
        if not entry:
            return
        entry = dict(entry)
        decoded = dict(entry.get("data") or {})

        if f"port_{self._port_num}" in decoded:
            port_key = f"port_{self._port_num}"
            port_data = dict(decoded.get(port_key) or {})
            target = port_data
            decoded[port_key] = port_data
        elif self._port_num == 1:
            target = decoded
        else:
            return

        target["is_watering"] = is_on
        target["valve_state"] = "irrigation" if is_on else "idle"

        entry["data"] = decoded
        sensors[self._sensor_key] = entry
        current["sensors"] = sensors
        self.coordinator.async_set_updated_data(current)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set_switch_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set_switch_state(False)

    async def _async_set_switch_state(self, is_on: bool) -> None:
        mid = self._sensor_info["mid"]
        addr = self._sensor_info["addr"]

        hubs = self.coordinator.data.get("hubs", [])
        hub = next((h for h in hubs if h.get("mid") == mid), {})
        device_name = hub.get("deviceName", "")
        product_key = hub.get("productKey", "")

        _LOGGER.debug(
            "Setting socket mid=%s addr=%s port=%s is_on=%s",
            mid, addr, self._port_num, is_on,
        )

        hid = self._sensor_info.get("hid")
        client = self.coordinator._client
        await client.control_work_mode(
            mid=mid,
            addr=addr,
            device_name=device_name,
            product_key=product_key,
            port=self._port_num,
            mode=1 if is_on else 0,
            duration=0,
            hid=hid,
        )
        await self.coordinator.async_request_refresh()
        self._apply_optimistic_port_update(is_on)
