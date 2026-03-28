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

from .const import DOMAIN, MODEL_VALVE_HUB
from .coordinator import HomGarCoordinator

_LOGGER = logging.getLogger(__name__)

DURATION_MIN_MINUTES = 1
DURATION_MAX_MINUTES = 60
DURATION_STEP_MINUTES = 1
DURATION_DEFAULT_MINUTES = 10


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
        if info.get("model") != MODEL_VALVE_HUB:
            continue

        decoded = info.get("data") or {}
        zones: dict = decoded.get("zones", {})

        for zone_num in sorted(zones.keys()):
            entities.append(
                HomGarZoneDurationNumber(coordinator, key, info, zone_num)
            )
            _LOGGER.debug(
                "Creating duration number entity: key=%s zone=%s",
                key, zone_num,
            )

    if entities:
        async_add_entities(entities)


class HomGarZoneDurationNumber(CoordinatorEntity, NumberEntity, RestoreEntity):
    """Configurable run duration (in minutes) for a single irrigation zone.

    The value is restored on HA restart via RestoreEntity.  When a valve is
    opened without an explicit duration override in the service call data,
    valve.py reads this entity's current value and converts it to seconds.
    """

    _attr_native_min_value = DURATION_MIN_MINUTES
    _attr_native_max_value = DURATION_MAX_MINUTES
    _attr_native_step = DURATION_STEP_MINUTES
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
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
        self._current_value: float = DURATION_DEFAULT_MINUTES

        hid = sensor_info["hid"]
        mid = sensor_info["mid"]
        addr = sensor_info["addr"]
        sub_name = sensor_info.get("sub_name") or f"Valve Hub {addr}"

        self._attr_unique_id = f"homgar_{hid}_{mid}_{addr}_zone{zone_num}_duration"
        self._attr_name = f"{sub_name} Zone {zone_num} Duration"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                restored = float(last_state.state)
                if DURATION_MIN_MINUTES <= restored <= DURATION_MAX_MINUTES:
                    self._current_value = restored
                    _LOGGER.debug(
                        "Restored duration for %s: %s min",
                        self._attr_unique_id, restored,
                    )
            except (ValueError, TypeError):
                pass

    @property
    def native_value(self) -> float:
        return self._current_value

    async def async_set_native_value(self, value: float) -> None:
        self._current_value = value
        self.async_write_ha_state()

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
