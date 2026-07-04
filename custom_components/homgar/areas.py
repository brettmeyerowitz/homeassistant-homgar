"""Area seeding for HomGar devices.

Home Assistant areas are seeded from the HomGar "home" name, but only on the
**first setup** of a config entry. After that the integration never creates or
(re)assigns areas, so a user who deletes the auto-created area keeps it deleted
across reloads (issue #70). Device name/model backfill still runs on every
reload (issue #63).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .const import CONF_GROUP_MULTI_ZONE_DEVICES, DOMAIN, zone_device_identifier
from .decoder import get_valve_ports

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


def _fallback_hub_name(hub_info: dict) -> str:
    model = hub_info.get("model")
    return (
        hub_info.get("name")
        or hub_info.get("displayModel")
        or (model if model and model != "Unknown" else None)
        or "RainPoint Hub"
    )


def seed_device_areas(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator,
    is_first_setup: bool,
) -> None:
    """Create an HA area per home and seed devices into it on first setup only.

    Area creation and assignment happen only when ``is_first_setup`` is true (a
    fresh config entry with no devices yet). On every subsequent reload the
    integration leaves areas alone: deleting an area in HA nulls the devices'
    ``area_id``, and recreating it on reload is exactly the #70 bug. New devices
    added to an existing install are still grouped via ``suggested_area`` at the
    moment they are first registered.

    Device name/model backfill is independent of area seeding and runs on every
    reload (issue #63).
    """
    from homeassistant.helpers import area_registry as ar, device_registry as dr

    data = coordinator.data
    if not data:
        return

    area_reg = ar.async_get(hass)
    device_reg = dr.async_get(hass)

    def _seed_area(home_name: str):
        """Return the area for ``home_name``, creating it only on first setup."""
        area = area_reg.async_get_area_by_name(home_name)
        if not area and is_first_setup:
            area = area_reg.async_create(home_name)
        return area

    hubs = data.get("hubs", [])
    if isinstance(hubs, dict):
        hubs = list(hubs.values())

    for hub_info in hubs:
        home_name = hub_info.get("homeName") or ""
        if not home_name:
            continue
        mid = hub_info.get("mid")
        if not mid:
            continue

        hub_device = device_reg.async_get_device(identifiers={(DOMAIN, f"rainpoint_hub_{mid}")})
        if not hub_device:
            continue

        update: dict = {}
        # Name/model backfill runs unconditionally (issue #63).
        if not hub_device.name:
            update["name"] = _fallback_hub_name(hub_info)
        if not hub_device.model:
            update["model"] = hub_info.get("model") or hub_info.get("displayModel") or "Unknown"
        # Area assignment only on first setup (issue #70).
        if is_first_setup and hub_device.area_id is None:
            area = _seed_area(home_name)
            if area:
                update["area_id"] = area.id
        if update:
            device_reg.async_update_device(hub_device.id, **update)

    # Everything below is pure area seeding — skip entirely after first setup so
    # deleted areas are not recreated and user-cleared devices are not reassigned.
    if not is_first_setup:
        return

    sensors = data.get("sensors", {})
    group_multi_zone = entry.options.get(CONF_GROUP_MULTI_ZONE_DEVICES, False)
    for sensor_info in sensors.values():
        home_name = sensor_info.get("home_name") or ""
        if not home_name:
            continue
        mid = sensor_info.get("mid")
        addr = sensor_info.get("addr")
        if mid is None or addr is None:
            continue

        area = _seed_area(home_name)
        if not area:
            continue

        device = device_reg.async_get_device(identifiers={(DOMAIN, f"{mid}_{addr}")})
        if device and device.area_id is None:
            device_reg.async_update_device(device.id, area_id=area.id)

        model = sensor_info.get("model")
        if group_multi_zone and model and len(get_valve_ports(model)) > 1:
            for port in get_valve_ports(model):
                zone_device = device_reg.async_get_device(
                    identifiers={(DOMAIN, zone_device_identifier(mid, addr, port))}
                )
                if zone_device and zone_device.area_id is None:
                    device_reg.async_update_device(zone_device.id, area_id=area.id)
