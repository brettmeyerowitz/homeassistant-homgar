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

from .const import DOMAIN

_OLD_HUB_IDENT = re.compile(r"^hub_\d+$")
_OLD_SENSOR_IDENT = re.compile(r"^\d+_\d+_\d+$")

_LOGGER = logging.getLogger(__name__)


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
