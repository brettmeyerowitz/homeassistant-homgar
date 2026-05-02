"""Migration utilities for the HomGar integration.

Handles v1->v2 unique_id and device registry cleanup.
Runs on every startup but is idempotent — skips work that is already done.
"""
from __future__ import annotations

import logging
import re

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er, device_registry as dr

from .const import (
    CONF_GROUP_MULTI_ZONE_DEVICES,
    controller_device_identifier,
    DOMAIN,
    format_port_device_name,
    zone_device_identifier,
)
from .decoder import get_valve_ports

_OLD_HUB_IDENT = re.compile(r"^hub_\d+$")
_OLD_SENSOR_IDENT = re.compile(r"^\d+_\d+_\d+$")
_ZONE_DEVICE_IDENT = re.compile(r"^\d+_\d+_zone\d+$")
_HUB_DEVICE_IDENT = re.compile(r"^rainpoint_hub_(?P<mid>\d+)$")
_HUB_DIAGNOSTIC_UID = re.compile(
    r"^rainpoint_hub_(?P<mid>\d+)_(?:device_id|firmware|mac|channel|broadcast)$"
)
_PER_ZONE_ENTITY_UID = re.compile(
    r"^rainpoint_(?P<mid>\d+)_(?P<addr>\d+)_(?:(?P<field>.+)_port(?P<sensor_port>\d+)|zone(?P<zone_port>\d+)(?:_duration)?)$"
)

_LOGGER = logging.getLogger(__name__)


def _fallback_hub_name(hub_info: dict) -> str:
    model = hub_info.get("model")
    return (
        hub_info.get("name")
        or hub_info.get("displayModel")
        or (model if model and model != "Unknown" else None)
        or "RainPoint Hub"
    )


async def async_migrate_unique_ids(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator,
) -> None:
    """Migrate v1 homgar_ unique_ids and remove stale devices.

    Idempotent — safe to run on every startup.

    Entity rename:
      homgar_{hid}_{mid}_{addr}_{suffix}  ->  rainpoint_{mid}_{addr}_{suffix}
      homgar_hub_{hid}_{suffix}           ->  rainpoint_hub_{mid}_{suffix}

    Device cleanup:
      Old-style devices (hub_{hid}, {hid}_{mid}_{addr}) with no entities
      attached are removed.
    """
    data = coordinator.data
    if not data:
        _LOGGER.warning("HomGar migrate: no coordinator data, skipping")
        return

    entity_reg = er.async_get(hass)

    sensors = data.get("sensors", {})
    hubs = data.get("hubs", [])
    if isinstance(hubs, dict):
        hubs = list(hubs.values())

    # --- Rename entity unique_ids ---
    all_entries = er.async_entries_for_config_entry(entity_reg, entry.entry_id)

    for sensor_info in sensors.values():
        hid = sensor_info.get("hid")
        mid = sensor_info.get("mid")
        addr = sensor_info.get("addr")
        if not (hid and mid is not None and addr is not None):
            continue
        old_prefix = f"homgar_{hid}_{mid}_{addr}_"
        new_prefix = f"rainpoint_{mid}_{addr}_"
        for entity_entry in all_entries:
            uid = entity_entry.unique_id
            if uid and uid.startswith(old_prefix):
                new_uid = f"{new_prefix}{uid[len(old_prefix):]}"
                try:
                    entity_reg.async_update_entity(entity_entry.entity_id, new_unique_id=new_uid)
                    _LOGGER.info("HomGar migrate uid: %s -> %s", uid, new_uid)
                except Exception as ex:  # noqa: BLE001
                    _LOGGER.warning("HomGar migrate uid failed %s: %s", uid, ex)

    # --- Rename hub entity unique_ids: homgar_hub_{hid}_* -> rainpoint_hub_{mid}_* ---
    # Build hid -> list of mids map (may be multiple hubs per home)
    hid_to_mids: dict[int, list[int]] = {}
    for hub_info in hubs:
        hid = hub_info.get("hid")
        mid = hub_info.get("mid")
        if hid and mid is not None:
            hid_to_mids.setdefault(int(hid), []).append(int(mid))

    for hid, mids in hid_to_mids.items():
        if len(mids) != 1:
            _LOGGER.info("HomGar migrate: skipping hub entities for hid=%s (ambiguous: %s mids)", hid, mids)
            continue
        mid = mids[0]
        old_hub_prefix = f"homgar_hub_{hid}_"
        new_hub_prefix = f"rainpoint_hub_{mid}_"
        old_hub_base = f"homgar_hub_{hid}"
        new_hub_base = f"rainpoint_hub_{mid}"
        for entity_entry in all_entries:
            uid = entity_entry.unique_id
            if not uid:
                continue
            if uid.startswith(old_hub_prefix):
                new_uid = f"{new_hub_prefix}{uid[len(old_hub_prefix):]}"
            elif uid == old_hub_base:
                new_uid = new_hub_base
            else:
                continue
            try:
                entity_reg.async_update_entity(entity_entry.entity_id, new_unique_id=new_uid)
                _LOGGER.info("HomGar migrate uid: %s -> %s", uid, new_uid)
            except Exception as ex:  # noqa: BLE001
                _LOGGER.warning("HomGar migrate uid failed %s: %s", uid, ex)

    device_reg = dr.async_get(hass)
    known_hub_mids = {str(hub_info.get("mid")) for hub_info in hubs if hub_info.get("mid") is not None}

    # --- Repair devices created from cloud rows with blank name/model strings ---
    for hub_info in hubs:
        mid = hub_info.get("mid")
        if mid is None:
            continue
        hub_dev = device_reg.async_get_device(identifiers={(DOMAIN, f"rainpoint_hub_{mid}")})
        if hub_dev is None:
            continue
        update: dict = {}
        if not hub_dev.name:
            update["name"] = _fallback_hub_name(hub_info)
        if not hub_dev.model:
            update["model"] = hub_info.get("model") or hub_info.get("displayModel") or "Unknown"
        if update:
            device_reg.async_update_device(hub_dev.id, **update)
            _LOGGER.info("HomGar migrate: repaired blank hub device metadata for mid=%s", mid)

    # --- Remove stale placeholder hub devices no longer returned by the cloud ---
    for device_entry in list(dr.async_entries_for_config_entry(device_reg, entry.entry_id)):
        idents = {i[1] for i in device_entry.identifiers}
        hub_mids = {
            match.group("mid")
            for ident in idents
            if (match := _HUB_DEVICE_IDENT.match(ident))
        }
        if not hub_mids or hub_mids & known_hub_mids:
            continue

        attached = er.async_entries_for_device(entity_reg, device_entry.id, include_disabled_entities=True)
        if not attached:
            device_reg.async_remove_device(device_entry.id)
            _LOGGER.info("HomGar migrate: removed stale empty hub device '%s' (%s)", device_entry.name, idents)
            continue

        if all(
            entity.unique_id and _HUB_DIAGNOSTIC_UID.match(entity.unique_id)
            for entity in attached
        ):
            for entity in attached:
                entity_reg.async_remove(entity.entity_id)
                _LOGGER.info("HomGar migrate: removed stale hub diagnostic entity %s", entity.unique_id)
            device_reg.async_remove_device(device_entry.id)
            _LOGGER.info("HomGar migrate: removed stale empty hub device '%s' (%s)", device_entry.name, idents)

    # --- Build known old MQTT device identifiers (hid_mid format) from coordinator data ---
    known_old_mqtt_idents: set[str] = set()
    for hub_info in hubs:
        hid = hub_info.get("hid")
        mid = hub_info.get("mid")
        if hid and mid is not None:
            known_old_mqtt_idents.add(f"{hid}_{mid}")

    # --- Delete entities on old MQTT devices, then remove the devices ---
    # Entities will be recreated on the correct hub device by platform setup
    for device_entry in list(dr.async_entries_for_config_entry(device_reg, entry.entry_id)):
        idents = {i[1] for i in device_entry.identifiers}
        if not (idents & known_old_mqtt_idents):
            continue
        for entity_entry in er.async_entries_for_device(entity_reg, device_entry.id, include_disabled_entities=True):
            _LOGGER.info("HomGar migrate: deleting MQTT entity %s from old device", entity_entry.unique_id)
            entity_reg.async_remove(entity_entry.entity_id)
        _LOGGER.info("HomGar migrate: removing old MQTT device '%s' (%s)", device_entry.name, idents)
        device_reg.async_remove_device(device_entry.id)

    _LOGGER.info("HomGar migrate: entity unique_id migration complete")

    # --- Remove old-style orphan sensor/hub devices (no entities attached) ---
    for device_entry in list(dr.async_entries_for_config_entry(device_reg, entry.entry_id)):
        idents = {i[1] for i in device_entry.identifiers}
        if not any(_OLD_HUB_IDENT.match(i) or _OLD_SENSOR_IDENT.match(i) for i in idents):
            continue
        attached = er.async_entries_for_device(entity_reg, device_entry.id, include_disabled_entities=True)
        if not attached:
            _LOGGER.info("HomGar migrate: removing orphan device '%s' (%s)", device_entry.name, idents)
            device_reg.async_remove_device(device_entry.id)


async def async_merge_wifi_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator,
) -> None:
    """Move entities from WiFi sub-devices ({mid}_{addr}) to hub device (rainpoint_hub_{mid}).

    Must run after platform setup so the hub device already exists in the registry.
    Idempotent — skips if sub-device not found.
    """
    data = coordinator.data
    if not data:
        return

    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    sensors = data.get("sensors", {})

    for sensor_info in sensors.values():
        if sensor_info.get("type_flag") != 1:
            continue
        mid = sensor_info.get("mid")
        addr = sensor_info.get("addr")
        if mid is None or addr is None:
            continue
        old_dev = device_reg.async_get_device(identifiers={(DOMAIN, f"{mid}_{addr}")})
        hub_dev = device_reg.async_get_device(identifiers={(DOMAIN, f"rainpoint_hub_{mid}")})
        if not (old_dev and hub_dev and old_dev.id != hub_dev.id):
            continue
        for entity_entry in er.async_entries_for_device(entity_reg, old_dev.id, include_disabled_entities=True):
            entity_reg.async_update_entity(entity_entry.entity_id, device_id=hub_dev.id)
            _LOGGER.info("HomGar migrate: moved WiFi entity %s to hub device", entity_entry.unique_id)
        device_reg.async_remove_device(old_dev.id)
        _LOGGER.info("HomGar migrate: merged WiFi sub-device mid=%s addr=%s into hub", mid, addr)


async def async_rehome_multi_zone_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator,
) -> None:
    """Assign per-zone entities to child devices when the option is enabled.

    Reversible and idempotent: entities move back to the parent controller
    device when the option is disabled again.
    """
    data = coordinator.data
    if not data:
        return

    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    sensors = data.get("sensors", {})
    sensors_by_key: dict[tuple[int, int], dict] = {}
    for sensor_info in sensors.values():
        mid = sensor_info.get("mid")
        addr = sensor_info.get("addr")
        model = sensor_info.get("model")
        if mid is None or addr is None or not model or len(get_valve_ports(model)) <= 1:
            continue
        sensors_by_key[(int(mid), int(addr))] = sensor_info

    group_by_zone = entry.options.get(CONF_GROUP_MULTI_ZONE_DEVICES, False)
    matched_entities = 0
    moved_entities = 0

    for entity_entry in er.async_entries_for_config_entry(entity_reg, entry.entry_id):
        uid = entity_entry.unique_id or ""
        match = _PER_ZONE_ENTITY_UID.match(uid)
        if not match:
            continue
        matched_entities += 1

        mid = int(match.group("mid"))
        addr = int(match.group("addr"))
        port = int(match.group("sensor_port") or match.group("zone_port") or 0)
        if port <= 0:
            continue

        sensor_info = sensors_by_key.get((mid, addr))
        if not sensor_info:
            continue

        parent_ident_str = controller_device_identifier(sensor_info)
        parent_ident = (DOMAIN, parent_ident_str)
        parent_dev = device_reg.async_get_device(identifiers={parent_ident})
        if parent_dev is None:
            create_kwargs = {
                "config_entry_id": entry.entry_id,
                "identifiers": {parent_ident},
                "manufacturer": "RainPoint",
                "model": sensor_info.get("model") or "Unknown",
                "name": sensor_info.get("sub_name") or f"Valve Hub {addr}",
                "suggested_area": sensor_info.get("home_name"),
            }
            if sensor_info.get("type_flag") != 1:
                create_kwargs["via_device"] = (DOMAIN, f"rainpoint_hub_{mid}")
            parent_dev = device_reg.async_get_or_create(**create_kwargs)

        target_dev = parent_dev
        if group_by_zone:
            zone_ident = (DOMAIN, zone_device_identifier(mid, addr, port))
            target_dev = device_reg.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={zone_ident},
                manufacturer="RainPoint",
                model=sensor_info.get("model") or "Unknown",
                name=format_port_device_name(
                    sensor_info.get("sub_name") or f"Valve Hub {addr}",
                    sensor_info,
                    port,
                ),
                via_device=parent_ident,
                suggested_area=sensor_info.get("home_name"),
            )

        if entity_entry.device_id != target_dev.id:
            entity_reg.async_update_entity(entity_entry.entity_id, device_id=target_dev.id)
            moved_entities += 1
            _LOGGER.info(
                "HomGar migrate: moved %s to %s",
                entity_entry.unique_id,
                next(iter(target_dev.identifiers))[1],
            )

    for device_entry in list(dr.async_entries_for_config_entry(device_reg, entry.entry_id)):
        idents = {i[1] for i in device_entry.identifiers}
        if not any(_ZONE_DEVICE_IDENT.match(i) for i in idents):
            continue
        attached = er.async_entries_for_device(entity_reg, device_entry.id, include_disabled_entities=True)
        if not attached:
            device_reg.async_remove_device(device_entry.id)
            _LOGGER.info("HomGar migrate: removed empty zone device '%s' (%s)", device_entry.name, idents)

    _LOGGER.info(
        "HomGar migrate: zone re-home complete for %s (group_by_zone=%s matched=%s moved=%s)",
        entry.title,
        group_by_zone,
        matched_entities,
        moved_entities,
    )
