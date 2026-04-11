from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.valve import (
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomGarCoordinator
from .decoder import get_valve_ports

_LOGGER = logging.getLogger(__name__)

# Default run duration used when HA opens a valve without an explicit duration.
# Users can override by calling the valve.open_valve service with a duration attr.
DEFAULT_DURATION_SECONDS = 600  # 10 minutes


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HomGarCoordinator = data["coordinator"]

    sensors_cfg = coordinator.data.get("sensors", {})
    entities: list[HomGarValveEntity] = []

    for key, info in sensors_cfg.items():
        model = info.get("model")
        valve_ports = get_valve_ports(model) if model else []
        if not valve_ports:
            continue

        # Create one valve entity per port declared in product_models.json dp[]
        for port in valve_ports:
            entities.append(
                HomGarValveEntity(coordinator, key, info, port)
            )
            _LOGGER.debug(
                "Creating valve entity: key=%s port=%s model=%s",
                key, port, model,
            )

    if entities:
        async_add_entities(entities)


class HomGarValveEntity(CoordinatorEntity, ValveEntity):
    """Represents a single irrigation zone on a HomGar valve hub."""

    _attr_should_poll = False
    _attr_reports_position = False
    _attr_supported_features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE

    def __init__(
        self,
        coordinator: HomGarCoordinator,
        sensor_key: str,
        sensor_info: dict,
        zone_num: int,
    ) -> None:
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._sensor_info = sensor_info
        self._zone_num = zone_num

        hid = sensor_info["hid"]
        mid = sensor_info["mid"]
        addr = sensor_info["addr"]
        sub_name = sensor_info.get("sub_name") or f"Valve Hub {addr}"

        self._attr_unique_id = f"rainpoint_{mid}_{addr}_zone{zone_num}"
        self._attr_name = f"{sub_name} Zone {zone_num}"

    # ------------------------------------------------------------------
    # Coordinator data helpers
    # ------------------------------------------------------------------

    @property
    def _port_data(self) -> dict | None:
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key)
        if not info:
            return None
        decoded = info.get("data")
        if not decoded:
            return None
        return decoded.get(f"port_{self._zone_num}")

    # ------------------------------------------------------------------
    # Entity properties
    # ------------------------------------------------------------------

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
    def is_closed(self) -> bool | None:
        port = self._port_data
        if port is None:
            return None
        is_watering = port.get("is_watering")
        if is_watering is None:
            return None
        return not is_watering

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        port = self._port_data
        if port:
            dur = port.get("current_session_duration")
            if dur is not None:
                attrs["duration_seconds"] = dur
            attrs["valve_state"] = port.get("valve_state")
        
        # Add firmware version from sensor info
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key) or {}
        firmware_version = info.get("firmware_version")
        if firmware_version:
            attrs["firmware_version"] = firmware_version
        
        # Add device timestamp from decoded data
        data = self.coordinator.data.get("sensors", {}).get(self._sensor_key, {}).get("data", {})
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
        sub_name = self._sensor_info.get("sub_name") or f"Valve Hub {addr}"
        model = self._sensor_info.get("model") or "Unknown"
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

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def _get_configured_duration_seconds(self) -> int:
        """Look up the companion duration number entity for this zone and convert
        its value (minutes) to seconds.  Falls back to DEFAULT_DURATION_SECONDS
        if the entity is not yet available.

        Uses the entity registry to resolve unique_id -> entity_id so the lookup
        is not sensitive to HA auto-generated entity_id naming."""
        from homeassistant.helpers import entity_registry as er
        mid = self._sensor_info["mid"]
        addr = self._sensor_info["addr"]
        unique_id = f"rainpoint_{mid}_{addr}_zone{self._zone_num}_duration"
        registry = er.async_get(self.hass)
        entity_id = registry.async_get_entity_id("number", "homgar", unique_id)
        if entity_id:
            state = self.hass.states.get(entity_id)
            if state is not None:
                try:
                    minutes = float(state.state)
                    return max(1, int(minutes * 60))
                except (ValueError, TypeError):
                    pass
        _LOGGER.debug(
            "Duration entity for unique_id=%s not found, falling back to default %ss",
            unique_id, DEFAULT_DURATION_SECONDS,
        )
        return DEFAULT_DURATION_SECONDS

    def _apply_response_state(self, raw_state: str | None) -> None:
        """Decode the state string returned by controlWorkMode and inject it
        into the coordinator data immediately, bypassing the poll cycle."""
        if not raw_state:
            return
        from .decoder import decode_payload
        model = self._sensor_info.get("model")
        decoded = decode_payload(model, raw_state) if model else {}
        if not decoded or "error" in decoded:
            return
        current = dict(self.coordinator.data)
        sensors = dict(current.get("sensors", {}))
        if self._sensor_key not in sensors:
            return
        entry = dict(sensors[self._sensor_key])
        entry["data"] = decoded
        sensors[self._sensor_key] = entry
        current["sensors"] = sensors
        self.coordinator.async_set_updated_data(current)

    # ------------------------------------------------------------------
    async def async_open_valve(self, **kwargs: Any) -> None:
        if "duration" in kwargs:
            duration = int(kwargs["duration"])
        else:
            duration = self._get_configured_duration_seconds()
        mid = self._sensor_info["mid"]
        addr = self._sensor_info["addr"]
        
        # Extract device_name and product_key from hub data instead of sensor_info
        hubs = self.coordinator.data.get("hubs", [])
        hub = next((h for h in hubs if h.get("mid") == mid), {})
        device_name = hub.get("deviceName", "")
        product_key = hub.get("productKey", "")

        _LOGGER.debug(
            "Opening valve mid=%s addr=%s zone=%s duration=%ss",
            mid, addr, self._zone_num, duration,
        )

        hid = self._sensor_info.get("hid")
        client = self.coordinator._client
        response_state = await client.control_work_mode(
            mid=mid,
            addr=addr,
            device_name=device_name,
            product_key=product_key,
            port=self._zone_num,
            mode=1,
            duration=duration,
            hid=hid,
        )
        # Bypass _apply_response_state to avoid crash - use refresh instead
        await self.coordinator.async_request_refresh()
        
        # OPTIMISTIC LOCAL UPDATE to prevent UI desync
        current = dict(self.coordinator.data)
        try:
            current["sensors"][self._sensor_key]["data"][f"port_{self._zone_num}"]["is_watering"] = True
            current["sensors"][self._sensor_key]["data"][f"port_{self._zone_num}"]["current_session_duration"] = duration
        except KeyError:
            pass
        self.coordinator.async_set_updated_data(current)
        return

    async def async_close_valve(self, **kwargs: Any) -> None:
        mid = self._sensor_info["mid"]
        addr = self._sensor_info["addr"]
        
        # Extract device_name and product_key from hub data instead of sensor_info
        hubs = self.coordinator.data.get("hubs", [])
        hub = next((h for h in hubs if h.get("mid") == mid), {})
        device_name = hub.get("deviceName", "")
        product_key = hub.get("productKey", "")

        _LOGGER.debug(
            "Closing valve mid=%s addr=%s zone=%s",
            mid, addr, self._zone_num,
        )

        hid = self._sensor_info.get("hid")
        client = self.coordinator._client
        response_state = await client.control_work_mode(
            mid=mid,
            addr=addr,
            device_name=device_name,
            product_key=product_key,
            port=self._zone_num,
            mode=0,
            duration=0,
            hid=hid,
        )
        # Bypass _apply_response_state to avoid crash - use refresh instead
        await self.coordinator.async_request_refresh()
        
        # OPTIMISTIC LOCAL UPDATE to prevent UI desync
        current = dict(self.coordinator.data)
        try:
            current["sensors"][self._sensor_key]["data"][f"port_{self._zone_num}"]["is_watering"] = False
            current["sensors"][self._sensor_key]["data"][f"port_{self._zone_num}"]["current_session_duration"] = 0
        except KeyError:
            pass
        self.coordinator.async_set_updated_data(current)
        return
