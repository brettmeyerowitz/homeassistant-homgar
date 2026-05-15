from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_GROUP_MULTI_ZONE_DEVICES,
    CONF_VALVE_DURATION_UNIT,
    DEFAULT_VALVE_DURATION_UNIT,
    VALVE_DURATION_UNIT_MINUTES,
    VALVE_DURATION_UNIT_SECONDS,
    controller_device_identifier,
    format_port_device_name,
    format_port_entity_name,
    zone_device_identifier,
)
from .coordinator import HomGarCoordinator
from .decoder import get_valve_ports

_LOGGER = logging.getLogger(__name__)

DURATION_MIN_SECONDS = 1
DURATION_MAX_SECONDS = 3600
DURATION_STEP_SECONDS = 1
DURATION_DEFAULT_SECONDS = 600
DURATION_MIN_MINUTES = 1
DURATION_MAX_MINUTES = 60
DURATION_STEP_MINUTES = 1


def _duration_unit_from_options(coordinator: HomGarCoordinator) -> str:
    """Return the configured duration number unit."""
    unit = coordinator._entry.options.get(CONF_VALVE_DURATION_UNIT, DEFAULT_VALVE_DURATION_UNIT)
    if unit == VALVE_DURATION_UNIT_SECONDS:
        return VALVE_DURATION_UNIT_SECONDS
    return VALVE_DURATION_UNIT_MINUTES


def _duration_seconds_from_native(value: float, unit: str) -> int:
    """Convert a duration number's native value to seconds."""
    if unit == VALVE_DURATION_UNIT_SECONDS:
        return int(value)
    return int(value * 60)


def _duration_native_from_seconds(seconds: int, unit: str) -> float:
    """Convert seconds to the duration number's configured native unit."""
    if unit == VALVE_DURATION_UNIT_SECONDS:
        return float(seconds)
    return seconds / 60


def _duration_bounds_seconds(unit: str) -> tuple[int, int]:
    """Return valid duration bounds in seconds for the configured unit."""
    if unit == VALVE_DURATION_UNIT_SECONDS:
        return DURATION_MIN_SECONDS, DURATION_MAX_SECONDS
    return DURATION_MIN_MINUTES * 60, DURATION_MAX_MINUTES * 60


def _clamp_duration_seconds(seconds: int, unit: str) -> int:
    """Clamp a duration to the range representable by the configured unit."""
    minimum, maximum = _duration_bounds_seconds(unit)
    return min(max(seconds, minimum), maximum)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HomGarCoordinator = data["coordinator"]

    sensors_cfg = coordinator.data.get("sensors", {})
    entities: list[HomGarZoneDurationNumber] = []

    for key, info in sensors_cfg.items():
        model = info.get("model")
        valve_ports = get_valve_ports(model) if model else []
        if not valve_ports:
            continue

        for port in valve_ports:
            entities.append(
                HomGarZoneDurationNumber(coordinator, key, info, port)
            )
            _LOGGER.debug(
                "Creating duration number entity: key=%s port=%s",
                key, port,
            )

    if entities:
        async_add_entities(entities)


class HomGarZoneDurationNumber(CoordinatorEntity, NumberEntity, RestoreEntity):
    """Configurable run duration for a single irrigation zone.

    The value is restored on HA restart via RestoreEntity.  When a valve is
    opened without an explicit duration override in the service call data,
    valve.py reads this entity's current value and converts it to seconds.
    """

    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-outline"

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
        self._duration_unit = _duration_unit_from_options(coordinator)
        self._current_seconds = _clamp_duration_seconds(
            DURATION_DEFAULT_SECONDS,
            self._duration_unit,
        )

        if self._duration_unit == VALVE_DURATION_UNIT_SECONDS:
            self._attr_native_min_value = DURATION_MIN_SECONDS
            self._attr_native_max_value = DURATION_MAX_SECONDS
            self._attr_native_step = DURATION_STEP_SECONDS
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
        else:
            self._attr_native_min_value = DURATION_MIN_MINUTES
            self._attr_native_max_value = DURATION_MAX_MINUTES
            self._attr_native_step = DURATION_STEP_MINUTES
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES

        hid = sensor_info["hid"]
        mid = sensor_info["mid"]
        addr = sensor_info["addr"]
        sub_name = sensor_info.get("sub_name") or f"Valve Hub {addr}"

        self._attr_unique_id = f"rainpoint_{mid}_{addr}_zone{zone_num}_duration"
        self._attr_name = format_port_entity_name(
            sub_name,
            sensor_info,
            zone_num,
            "Duration",
            use_device_prefix=(
                self.coordinator._entry.options.get(CONF_GROUP_MULTI_ZONE_DEVICES, False)
                and len(get_valve_ports(sensor_info.get("model"))) > 1
            ),
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                restored = float(last_state.state)
                restored_unit = last_state.attributes.get("unit_of_measurement")
                if restored_unit == UnitOfTime.SECONDS:
                    restored_seconds = int(restored)
                else:
                    # Legacy duration entities were always stored as minutes.
                    restored_seconds = int(restored * 60)
                self._current_seconds = _clamp_duration_seconds(
                    restored_seconds,
                    self._duration_unit,
                )
                if DURATION_MIN_SECONDS <= restored_seconds <= DURATION_MAX_SECONDS:
                    _LOGGER.debug(
                        "Restored duration for %s: %ss",
                        self._attr_unique_id, self._current_seconds,
                    )
            except (ValueError, TypeError):
                pass

    @property
    def native_value(self) -> float:
        return _duration_native_from_seconds(self._current_seconds, self._duration_unit)

    async def async_set_native_value(self, value: float) -> None:
        seconds = _duration_seconds_from_native(float(value), self._duration_unit)
        self._current_seconds = _clamp_duration_seconds(seconds, self._duration_unit)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "duration_unit": self._duration_unit,
            "duration_seconds": self._current_seconds,
        }
        
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
        parent_ident = controller_device_identifier(self._sensor_info)
        if (
            self.coordinator._entry.options.get(CONF_GROUP_MULTI_ZONE_DEVICES, False)
            and len(get_valve_ports(model)) > 1
        ):
            return {
                "identifiers": {(DOMAIN, zone_device_identifier(mid, addr, self._zone_num))},
                "name": format_port_device_name(sub_name, self._sensor_info, self._zone_num),
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
