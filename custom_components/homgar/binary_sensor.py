from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomGarCoordinator
from .sensor import HomGarSensorBase


class HomGarRainBinarySensor(HomGarSensorBase, BinarySensorEntity):
    """Binary sensor for rain state on supported sensor models."""

    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_icon = "mdi:weather-rainy"

    def __init__(
        self,
        coordinator: HomGarCoordinator,
        sensor_key: str,
        sensor_info: dict,
    ) -> None:
        base_slug = sensor_key
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        sub_name = sensor_info.get("sub_name") or "Sensor"
        self._attr_unique_id = f"rainpoint_{base_slug}_rain_detected"
        self._attr_name = f"{sub_name} Rained"

    @property
    def is_on(self) -> bool | None:
        data = self._sensor_data or {}
        value = data.get("rain_detected")
        return value if isinstance(value, bool) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        state = self.is_on
        if state is None:
            attrs["state_label"] = "Unknown"
        else:
            attrs["state_label"] = "Rained" if state else "Not rained"
        return attrs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HomGarCoordinator = entry_data["coordinator"]

    sensors_cfg = coordinator.data.get("sensors", {})
    entities: list[CoordinatorEntity] = []

    for key, info in sensors_cfg.items():
        data = info.get("data") or {}
        if "rain_detected" in data:
            entities.append(HomGarRainBinarySensor(coordinator, key, info))

    if entities:
        async_add_entities(entities)
