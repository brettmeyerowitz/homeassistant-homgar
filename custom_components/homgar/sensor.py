from __future__ import annotations

import logging
import re
from typing import Any

from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODEL_MOISTURE_SIMPLE, MODEL_MOISTURE_FULL, MODEL_RAIN
from .coordinator import HomGarCoordinator

_LOGGER = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HomGarCoordinator = data["coordinator"]

    sensors_cfg = coordinator.data.get("sensors", {})

    entities: list[HomGarSensorBase] = []

    for key, info in sensors_cfg.items():
        model = info.get("model")
        sub_name = info.get("sub_name") or f"addr_{info['addr']}"
        home_name = info.get("home_name") or ""
        base_slug_parts = []
        if home_name:
            base_slug_parts.append(_slugify(home_name))
        base_slug_parts.append(_slugify(sub_name))
        base_slug = "_".join(base_slug_parts)

        if model == MODEL_MOISTURE_SIMPLE:
            # Moisture only
            entities.append(
                HomGarMoisturePercentSensor(
                    coordinator, key, info, base_slug, simple=True
                )
            )
        elif model == MODEL_MOISTURE_FULL:
            # Moisture + temp + lux
            entities.append(
                HomGarMoisturePercentSensor(
                    coordinator, key, info, base_slug, simple=False
                )
            )
            entities.append(
                HomGarTemperatureSensor(
                    coordinator, key, info, base_slug
                )
            )
            entities.append(
                HomGarIlluminanceSensor(
                    coordinator, key, info, base_slug
                )
            )
        elif model == MODEL_RAIN:
            entities.append(
                HomGarRainSensor(
                    coordinator,
                    key,
                    info,
                    base_slug,
                    "rain_last_hour_mm",
                    "rain last hour",
                )
            )
            entities.append(
                HomGarRainSensor(
                    coordinator,
                    key,
                    info,
                    base_slug,
                    "rain_last_24h_mm",
                    "rain last 24h",
                )
            )
            entities.append(
                HomGarRainSensor(
                    coordinator,
                    key,
                    info,
                    base_slug,
                    "rain_last_7d_mm",
                    "rain last 7d",
                )
            )
            entities.append(
                HomGarRainSensor(
                    coordinator,
                    key,
                    info,
                    base_slug,
                    "rain_total_mm",
                    "rain total",
                )
            )
        else:
            _LOGGER.debug("Skipping unsupported model %s", model)

    if entities:
        async_add_entities(entities)


class HomGarSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for HomGar sensors."""

    _attr_should_poll = False

    def __init__(
        self,
        coordinator: HomGarCoordinator,
        sensor_key: str,
        sensor_info: dict,
        base_slug: str,
    ) -> None:
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._sensor_info = sensor_info
        self._base_slug = base_slug

    @property
    def _sensor_data(self) -> dict | None:
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key)
        if not info:
            return None
        return info.get("data")

    @property
    def available(self) -> bool:
        return self._sensor_data is not None

    @property
    def device_info(self) -> dict[str, Any]:
        """Represent each subDevice as its own HA device."""
        hid = self._sensor_info["hid"]
        mid = self._sensor_info["mid"]
        addr = self._sensor_info["addr"]
        sub_name = self._sensor_info.get("sub_name") or f"Sensor {addr}"
        model = self._sensor_info.get("model") or "Unknown"

        return {
            # Unique per subdevice
            "identifiers": {(DOMAIN, f"{hid}_{mid}_{addr}")},
            "name": f"{sub_name}",
            "manufacturer": "HomGar",
            "model": model,
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._sensor_data or {}
        attrs: dict[str, Any] = {}
        if "rssi_dbm" in data:
            attrs["rssi_dbm"] = data["rssi_dbm"]
        if "battery_status_code" in data:
            attrs["battery_status_code"] = data["battery_status_code"]

        # Add last_updated from the latest raw_status time (ms since epoch)
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key) or {}
        raw_status = info.get("raw_status") or {}
        ts = raw_status.get("time")
        if ts:
            try:
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                attrs["last_updated"] = dt.isoformat()
            except Exception:  # noqa: BLE001
                # If anything goes wrong, we simply omit last_updated
                pass

        return attrs


class HomGarMoisturePercentSensor(HomGarSensorBase):
    """Moisture % sensor."""

    _attr_device_class = SensorDeviceClass.MOISTURE
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: HomGarCoordinator,
        sensor_key: str,
        sensor_info: dict,
        base_slug: str,
        simple: bool,
    ) -> None:
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._simple = simple
        model = sensor_info.get("model", "")
        sub_name = sensor_info.get("sub_name") or "Sensor"
        self._attr_unique_id = f"homgar_{base_slug}_moisture_percent"
        self._attr_name = f"{sub_name} Moisture Percent"

    @property
    def native_value(self) -> float | None:
        data = self._sensor_data
        if not data:
            return None
        return data.get("moisture_percent")


class HomGarTemperatureSensor(HomGarSensorBase):
    """Temperature sensor for HCS021FRF."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: HomGarCoordinator,
        sensor_key: str,
        sensor_info: dict,
        base_slug: str,
    ) -> None:
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        sub_name = sensor_info.get("sub_name") or "Sensor"
        self._attr_unique_id = f"homgar_{base_slug}_temperature"
        self._attr_name = f"{sub_name} Temperature"

    @property
    def native_value(self) -> float | None:
        data = self._sensor_data
        if not data:
            return None
        return round(data.get("temperature_c"), 1) if data.get("temperature_c") is not None else None


class HomGarIlluminanceSensor(HomGarSensorBase):
    """Illuminance sensor for HCS021FRF."""

    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = "lx"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: HomGarCoordinator,
        sensor_key: str,
        sensor_info: dict,
        base_slug: str,
    ) -> None:
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        sub_name = sensor_info.get("sub_name") or "Sensor"
        self._attr_unique_id = f"homgar_{base_slug}_illuminance"
        self._attr_name = f"{sub_name} Illuminance"

    @property
    def native_value(self) -> float | None:
        data = self._sensor_data
        if not data:
            return None
        return data.get("illuminance_lux")


class HomGarRainSensor(HomGarSensorBase):
    """Rain sensor (various windows)."""

    _attr_device_class = SensorDeviceClass.PRECIPITATION
    _attr_native_unit_of_measurement = "mm"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: HomGarCoordinator,
        sensor_key: str,
        sensor_info: dict,
        base_slug: str,
        data_key: str,
        label: str,
    ) -> None:
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._data_key = data_key
        sub_name = sensor_info.get("sub_name") or "Rain Sensor"
        slug_suffix = data_key
        self._attr_unique_id = f"homgar_{base_slug}_{slug_suffix}"
        # Format rain labels: convert to "Rain (Last X)" style
        window = label.replace("rain", "").strip()
        window_map = {
            "last hour": "Last Hour",
            "last 24h": "Last 24 Hours",
            "last 7d": "Last 7 Days",
            "total": "Total",
        }
        window_fmt = window_map.get(window, window.title())
        self._attr_name = f"{sub_name} Rain ({window_fmt})"

    @property
    def native_value(self) -> float | None:
        data = self._sensor_data
        if not data:
            return None
        val = data.get(self._data_key)
        if val is None:
            return None
        return round(val, 1)