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

from .const import DOMAIN, MODEL_VALVE_HUB, MODEL_VALVE_213, MODEL_VALVE_245
from .coordinator import HomGarCoordinator
from .homgar_api import decode_valve_hub
# build_valve_open_command / build_valve_close_command retained in homgar_api for reference

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
        if model not in [MODEL_VALVE_HUB, MODEL_VALVE_213, MODEL_VALVE_245]:
            continue

        decoded = info.get("data") or {}
        zones: dict = decoded.get("zones", {})

        # Create one valve entity per zone that reported in the payload.
        # Zones absent from the payload are not created - avoids phantom entities
        # if the device reports fewer zones than the model name implies.
        for zone_num in sorted(zones.keys()):
            entities.append(
                HomGarValveEntity(coordinator, key, info, zone_num)
            )
            _LOGGER.debug(
                "Creating valve entity: key=%s zone=%s model=%s",
                key, zone_num, info.get("model"),
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

        self._attr_unique_id = f"homgar_{hid}_{mid}_{addr}_zone{zone_num}"
        self._attr_name = f"{sub_name} Zone {zone_num}"

    # ------------------------------------------------------------------
    # Coordinator data helpers
    # ------------------------------------------------------------------

    @property
    def _zone_data(self) -> dict | None:
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key)
        if not info:
            return None
        decoded = info.get("data")
        if not decoded:
            return None
        return decoded.get("zones", {}).get(self._zone_num)

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
        return decoded.get("hub_online", False)

    @property
    def is_closed(self) -> bool | None:
        zone = self._zone_data
        if zone is None or zone.get("open") is None:
            return None
        return not zone["open"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        zone = self._zone_data
        if zone:
            dur = zone.get("duration_seconds")
            if dur is not None:
                attrs["duration_seconds"] = dur
            attrs["state_raw"] = zone.get("state_raw")
        
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
        hid = self._sensor_info["hid"]
        mid = self._sensor_info["mid"]
        addr = self._sensor_info["addr"]
        sub_name = self._sensor_info.get("sub_name") or f"Valve Hub {addr}"
        model = self._sensor_info.get("model") or "Unknown"
        return {
            "identifiers": {(DOMAIN, f"{hid}_{mid}_{addr}")},
            "name": sub_name,
            "manufacturer": "HomGar",
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
        hid = self._sensor_info["hid"]
        mid = self._sensor_info["mid"]
        addr = self._sensor_info["addr"]
        unique_id = f"homgar_{hid}_{mid}_{addr}_zone{self._zone_num}_duration"
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
        into the coordinator data immediately, bypassing the poll cycle.
        The API often returns a stale cached payload on the next poll so this
        ensures HA reflects the actual device state without delay."""
        if not raw_state:
            return
        decoded = decode_valve_hub(raw_state)
        if not decoded:
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
        device_name = self._sensor_info.get("device_name") or ""
        product_key = self._sensor_info.get("product_key") or ""

        _LOGGER.debug(
            "Opening valve mid=%s addr=%s zone=%s duration=%ss",
            mid, addr, self._zone_num, duration,
        )

        client = self.coordinator._client
        response_state = await client.control_work_mode(
            mid=mid,
            addr=addr,
            device_name=device_name,
            product_key=product_key,
            port=self._zone_num,
            mode=1,
            duration=duration,
        )
        self._apply_response_state(response_state)

    async def async_close_valve(self, **kwargs: Any) -> None:
        mid = self._sensor_info["mid"]
        addr = self._sensor_info["addr"]
        device_name = self._sensor_info.get("device_name") or ""
        product_key = self._sensor_info.get("product_key") or ""

        _LOGGER.debug(
            "Closing valve mid=%s addr=%s zone=%s",
            mid, addr, self._zone_num,
        )

        client = self.coordinator._client
        response_state = await client.control_work_mode(
            mid=mid,
            addr=addr,
            device_name=device_name,
            product_key=product_key,
            port=self._zone_num,
            mode=0,
            duration=0,
        )
        self._apply_response_state(response_state)
