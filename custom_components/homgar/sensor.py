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

from .const import (
    DOMAIN,
    MODEL_MOISTURE_SIMPLE,
    MODEL_MOISTURE_FULL,
    MODEL_RAIN,
    MODEL_TEMPHUM,
    MODEL_FLOWMETER,
    MODEL_CO2,
    MODEL_POOL,
    MODEL_DISPLAY_HUB
)
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
        _LOGGER.debug("Creating sensor entity: key=%s, model=%s, sub_name=%s, home_name=%s, base_slug=%s, info=%s", key, model, sub_name, home_name, base_slug, info)

        if model == MODEL_DISPLAY_HUB:
            data = info.get("data", {})
            readings = data.get("readings", {}) if data else {}
            for reading_key, reading_val in readings.items():
                entities.append(DisplayHubReadingSensor(coordinator, key, info, base_slug, reading_key))
        elif model == MODEL_MOISTURE_SIMPLE:
            entities.append(HomGarMoisturePercentSensor(coordinator, key, info, base_slug, simple=True))
        elif model == MODEL_MOISTURE_FULL:
            entities.append(HomGarMoisturePercentSensor(coordinator, key, info, base_slug, simple=False))
            entities.append(HomGarTemperatureSensor(coordinator, key, info, base_slug))
            entities.append(HomGarIlluminanceSensor(coordinator, key, info, base_slug))
        elif model == MODEL_RAIN:
            entities.append(HomGarRainSensor(coordinator, key, info, base_slug, "rain_last_hour_mm", "rain last hour"))
            entities.append(HomGarRainSensor(coordinator, key, info, base_slug, "rain_last_24h_mm", "rain last 24h"))
            entities.append(HomGarRainSensor(coordinator, key, info, base_slug, "rain_last_7d_mm", "rain last 7d"))
            entities.append(HomGarRainSensor(coordinator, key, info, base_slug, "rain_total_mm", "rain total"))
        elif model == MODEL_TEMPHUM:
            entities.append(HomGarTempHumCurrentSensor(coordinator, key, info, base_slug))
            entities.append(HomGarTempHumHighSensor(coordinator, key, info, base_slug))
            entities.append(HomGarTempHumLowSensor(coordinator, key, info, base_slug))
            entities.append(HomGarTempHumHumidityCurrentSensor(coordinator, key, info, base_slug))
            entities.append(HomGarTempHumHumidityHighSensor(coordinator, key, info, base_slug))
            entities.append(HomGarTempHumHumidityLowSensor(coordinator, key, info, base_slug))
        elif model == MODEL_FLOWMETER:
            entities.append(HomGarFlowCurrentUsedSensor(coordinator, key, info, base_slug))
            entities.append(HomGarFlowCurrentDurationSensor(coordinator, key, info, base_slug))
            entities.append(HomGarFlowLastUsedSensor(coordinator, key, info, base_slug))
            entities.append(HomGarFlowLastUsedDurationSensor(coordinator, key, info, base_slug))
            entities.append(HomGarFlowTotalTodaySensor(coordinator, key, info, base_slug))
            entities.append(HomGarFlowTotalSensor(coordinator, key, info, base_slug))
            entities.append(HomGarFlowBatterySensor(coordinator, key, info, base_slug))
        elif model == MODEL_CO2:
            entities.append(HomGarCO2Sensor(coordinator, key, info, base_slug))
            entities.append(HomGarCO2LowSensor(coordinator, key, info, base_slug))
            entities.append(HomGarCO2HighSensor(coordinator, key, info, base_slug))
            entities.append(HomGarCO2TempSensor(coordinator, key, info, base_slug))
            entities.append(HomGarCO2HumiditySensor(coordinator, key, info, base_slug))
            entities.append(HomGarCO2BatterySensor(coordinator, key, info, base_slug))
        elif model == MODEL_POOL:
            entities.append(HomGarPoolCurrentTempSensor(coordinator, key, info, base_slug))
            entities.append(HomGarPoolHighTempSensor(coordinator, key, info, base_slug))
            entities.append(HomGarPoolLowTempSensor(coordinator, key, info, base_slug))
            entities.append(HomGarPoolBatterySensor(coordinator, key, info, base_slug))

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
        _LOGGER.debug("Initialized HomGarSensorBase: sensor_key=%s, sensor_info=%s, base_slug=%s", sensor_key, sensor_info, base_slug)

    @property
    def _sensor_data(self) -> dict | None:
        sensors = self.coordinator.data.get("sensors", {})
        info = sensors.get(self._sensor_key)
        if not info:
            _LOGGER.debug("Sensor key %s not found in coordinator data", self._sensor_key)
            return None
        data = info.get("data")
        _LOGGER.debug("Sensor key %s data: %s", self._sensor_key, data)
        return data

    @property
    def available(self) -> bool:
        available = self._sensor_data is not None
        _LOGGER.debug("Sensor %s available: %s", self._sensor_key, available)
        return available

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        _LOGGER.debug("Sensor entity added to hass: %s", self._sensor_key)

    def _handle_coordinator_update(self) -> None:
        _LOGGER.debug("Coordinator update for sensor: %s", self._sensor_key)
        super()._handle_coordinator_update()

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
        value = data.get("moisture_percent") if data else None
        _LOGGER.debug("native_value for %s (moisture_percent): %s", self._sensor_key, value)
        return value


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
        value = round(data.get("temperature_c"), 1) if data and data.get("temperature_c") is not None else None
        _LOGGER.debug("native_value for %s (temperature_c): %s", self._sensor_key, value)
        return value


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
        value = data.get("illuminance_lux") if data else None
        _LOGGER.debug("native_value for %s (illuminance_lux): %s", self._sensor_key, value)
        return value


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


# HWS019WRF-V2 (Display Hub)
class DisplayHubReadingSensor(HomGarSensorBase):
    """Sensor for each Display Hub reading."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug, reading_key):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._reading_key = reading_key
        self._attr_unique_id = f"homgar_{base_slug}_displayhub_{reading_key}"
        sub_name = sensor_info.get("sub_name") or "Display Hub"
        self._attr_name = f"{sub_name} {reading_key}"

    @property
    def native_value(self):
        data = self._sensor_data
        if not data:
            return None
        readings = data.get("readings", {})
        value = readings.get(self._reading_key)
        try:
            return float(value)
        except (TypeError, ValueError):
            return value


# HCS014ARF (Temperature/Humidity)
class HomGarTempHumCurrentSensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_temphum_current"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Current Temperature"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("tempcurrent") if data else None


class HomGarTempHumHighSensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_temphum_high"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} High Temperature"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("temphigh") if data else None


class HomGarTempHumLowSensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_temphum_low"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Low Temperature"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("templow") if data else None


class HomGarTempHumHumidityCurrentSensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_temphum_humidity_current"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Current Humidity"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("humiditycurrent") if data else None


class HomGarTempHumHumidityHighSensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_temphum_humidity_high"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} High Humidity"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("humidityhigh") if data else None


class HomGarTempHumHumidityLowSensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_temphum_humidity_low"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Low Humidity"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("humiditylow") if data else None


# HCS008FRF (Flowmeter)
class HomGarFlowCurrentUsedSensor(HomGarSensorBase):
    _attr_native_unit_of_measurement = "L"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_flow_current_used"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Flow Current Used"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("flowcurrentused") if data else None


class HomGarFlowCurrentDurationSensor(HomGarSensorBase):
    _attr_native_unit_of_measurement = "s"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_flow_current_duration"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Flow Current Duration"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("flowcurrenduration") if data else None


class HomGarFlowLastUsedSensor(HomGarSensorBase):
    _attr_native_unit_of_measurement = "L"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_flow_last_used"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Flow Last Used"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("flowlastused") if data else None


class HomGarFlowLastUsedDurationSensor(HomGarSensorBase):
    _attr_native_unit_of_measurement = "s"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_flow_last_used_duration"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Flow Last Used Duration"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("flowlastusedduration") if data else None


class HomGarFlowTotalTodaySensor(HomGarSensorBase):
    _attr_native_unit_of_measurement = "L"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_flow_total_today"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Flow Total Today"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("flowtotaltoday") if data else None


class HomGarFlowTotalSensor(HomGarSensorBase):
    _attr_native_unit_of_measurement = "L"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_flow_total"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Flow Total"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("flowtotal") if data else None


class HomGarFlowBatterySensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_flow_battery"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Flow Battery"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("flowbatt") if data else None


# HCS0530THO (CO2/Temp/Humidity)
class HomGarCO2Sensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.CO2
    _attr_native_unit_of_measurement = "ppm"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_co2"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} CO2"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("co2") if data else None


class HomGarCO2LowSensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.CO2
    _attr_native_unit_of_measurement = "ppm"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_co2_low"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} CO2 Low"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("co2low") if data else None


class HomGarCO2HighSensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.CO2
    _attr_native_unit_of_measurement = "ppm"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_co2_high"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} CO2 High"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("co2high") if data else None


class HomGarCO2TempSensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_co2_temp"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} CO2 Temperature"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("co2temp") if data else None


class HomGarCO2HumiditySensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_co2_humidity"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} CO2 Humidity"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("co2humidity") if data else None


class HomGarCO2BatterySensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_co2_battery"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} CO2 Battery"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("co2batt") if data else None


# HCS0528ARF (Pool/Temperature)
class HomGarPoolCurrentTempSensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_pool_current_temp"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Pool Current Temperature"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("tempcurrent") if data else None


class HomGarPoolHighTempSensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_pool_high_temp"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Pool High Temperature"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("temphigh") if data else None


class HomGarPoolLowTempSensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_pool_low_temp"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Pool Low Temperature"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("templow") if data else None


class HomGarPoolBatterySensor(HomGarSensorBase):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sensor_key, sensor_info, base_slug):
        super().__init__(coordinator, sensor_key, sensor_info, base_slug)
        self._attr_unique_id = f"homgar_{base_slug}_pool_battery"
        self._attr_name = f"{sensor_info.get('sub_name', 'Sensor')} Pool Battery"

    @property
    def native_value(self):
        data = self._sensor_data
        return data.get("tempbatt") if data else None
