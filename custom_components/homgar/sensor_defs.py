"""
sensor_defs.py — Field-to-HA-sensor mapping for v3 decoder output.

FIELD_SENSOR_MAP maps every field name that decode_payload() can return to a
SensorDef describing how to represent it in Home Assistant.

Fields mapped to None are handled by other platforms (valve.py) and must NOT
be created as sensor entities.

Fields absent from this map are silently ignored — they may be internal
decoder fields (port_number, dp_flag, error) or fields not yet mapped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    EntityCategory,
    UnitOfTemperature,
    UnitOfElectricPotential,
    PERCENTAGE,
    CONCENTRATION_PARTS_PER_MILLION,
    LIGHT_LUX,
    UnitOfPressure,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
    UnitOfLength,
    UnitOfTime,
    UnitOfSpeed,
)


@dataclass
class SensorDef:
    """Describes how a decoded field maps to a HA sensor entity."""

    device_class: SensorDeviceClass | None = None
    unit: str | None = None
    state_class: SensorStateClass | None = None
    entity_category: EntityCategory | None = None
    icon: str | None = None
    name: str | None = None


FIELD_SENSOR_MAP: dict[str, SensorDef | None] = {
    # --- Temperature / humidity / environment ---
    "temperature": SensorDef(
        device_class=SensorDeviceClass.TEMPERATURE,
        unit=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "humidity": SensorDef(
        device_class=SensorDeviceClass.HUMIDITY,
        unit=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "soil_moisture": SensorDef(
        device_class=SensorDeviceClass.MOISTURE,
        unit=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "carbon_dioxide": SensorDef(
        device_class=SensorDeviceClass.CO2,
        unit=CONCENTRATION_PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "carbon_dioxide_warning_threshold": SensorDef(
        unit=CONCENTRATION_PARTS_PER_MILLION,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:molecule-co2",
        name="CO2 Warning Threshold",
    ),
    "illuminance": SensorDef(
        device_class=SensorDeviceClass.ILLUMINANCE,
        unit=LIGHT_LUX,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "air_pressure": SensorDef(
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        unit=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "wind_speed": SensorDef(
        device_class=SensorDeviceClass.WIND_SPEED,
        unit=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),

    # --- Water / flow ---
    "total_water_volume": SensorDef(
        device_class=SensorDeviceClass.WATER,
        unit=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "last_water_volume": SensorDef(
        device_class=SensorDeviceClass.WATER,
        unit=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL,
        name="Last Session Volume",
    ),
    "today_water_volume": SensorDef(
        device_class=SensorDeviceClass.WATER,
        unit=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Today's Water Volume",
    ),
    "current_water_volume": SensorDef(
        device_class=SensorDeviceClass.WATER,
        unit=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL,
        name="Current Session Volume",
    ),
    "flow_rate": SensorDef(
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        unit=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "current_session_duration": SensorDef(
        device_class=SensorDeviceClass.DURATION,
        unit=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        name="Session Duration",
    ),

    # --- Rain ---
    "precipitation_total": SensorDef(
        device_class=SensorDeviceClass.PRECIPITATION,
        unit=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Rain Total",
    ),
    "precipitation_1h": SensorDef(
        device_class=SensorDeviceClass.PRECIPITATION,
        unit=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        name="Rain Last Hour",
    ),
    "precipitation_24h": SensorDef(
        device_class=SensorDeviceClass.PRECIPITATION,
        unit=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        name="Rain Last 24h",
    ),
    "precipitation_7d": SensorDef(
        device_class=SensorDeviceClass.PRECIPITATION,
        unit=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        name="Rain Last 7 Days",
    ),

    # --- Diagnostics ---
    "battery_level": SensorDef(
        device_class=SensorDeviceClass.BATTERY,
        unit=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "signal_strength": SensorDef(
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        unit="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "alarm": SensorDef(
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:bell-alert",
        name="Alarm",
    ),
    "event_time": SensorDef(
        device_class=SensorDeviceClass.TIMESTAMP,
        name="Current Step End Time",
    ),
    "event_time2": SensorDef(
        device_class=SensorDeviceClass.TIMESTAMP,
        name="Schedule End Time",
    ),
    "irrigation_end_time": SensorDef(
        device_class=SensorDeviceClass.TIMESTAMP,
        name="Irrigation End Time",
        icon="mdi:timer-end",
    ),
    "cycle_type": SensorDef(
        icon="mdi:sprinkler-variant",
        name="Cycle Type",
    ),

    # --- Handled by valve.py — do NOT create sensor entities for these ---
    "valve_state": None,
    "is_watering": None,

    # --- Internal decoder fields — never create entities for these ---
    "flow_rate_unit": None,
    "port_number": None,
    "dp_flag": None,
    "error": None,
}


def sensor_fields_for_data(data: dict) -> list[str]:
    """
    Return the list of field names in a decoded data dict that should become
    sensor entities (i.e. present in data AND mapped to a non-None SensorDef).
    """
    return [
        f for f in data
        if f in FIELD_SENSOR_MAP and FIELD_SENSOR_MAP[f] is not None
    ]
