import logging
import time
import asyncio
from datetime import datetime, timedelta

from aiohttp import ClientError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_GROUP_MULTI_ZONE_DEVICES,
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    CONF_APP_TYPE,
    CONF_HIDS,
    controller_device_identifier,
    zone_device_identifier,
)
from .coordinator import HomGarCoordinator
from .decoder import _MODELS, get_switch_ports, get_valve_ports  # noqa: F401 — imported here to trigger eager file load in executor
from .api import HomGarClient
from .mqtt_client import HomGarMQTTClient, PAHO_AVAILABLE

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor", "valve", "switch", "number"]
_MQTT_RENEWAL_BACKOFF_SECONDS = (30, 60, 300, 900)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Legacy YAML setup - not used."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HomGar from a config entry."""
    session = async_get_clientsession(hass)

    area_code = entry.data["area_code"]
    email = entry.data["email"]
    password = entry.data["password"]
    # Default existing users to HomGar for backward compatibility
    app_type = entry.data.get(CONF_APP_TYPE, "homgar")

    client = HomGarClient(area_code, email, password, session, app_type)
    # Restore tokens if present
    client.restore_tokens(entry.data)

    # If MQTT credentials weren't stored, do a fresh login to obtain them
    from .const import CONF_MQTT_PRODUCT_KEY
    if not entry.data.get(CONF_MQTT_PRODUCT_KEY):
        try:
            await client.login()
        except Exception as err:
            raise ConfigEntryNotReady(f"HomGar [{entry.title}]: login failed: {err}") from err

    coordinator = HomGarCoordinator(hass, client, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"HomGar [{entry.title}]: initial data fetch failed: {err}") from err

    # Persist MQTT credentials to config entry if freshly obtained via login
    mqtt_creds = client.get_mqtt_credentials()
    if mqtt_creds.get("product_key") and not entry.data.get(CONF_MQTT_PRODUCT_KEY):
        hass.config_entries.async_update_entry(entry, data={**entry.data, **client.export_tokens()})

    # Migrate v1->v2 unique_ids before platform setup so renamed IDs don't
    # collide with freshly registered entities
    from .migrate import (
        async_migrate_unique_ids,
        async_merge_wifi_devices,
        async_rehome_multi_zone_entities,
    )
    await async_migrate_unique_ids(hass, entry, coordinator)

    # Prepare entry data storage early so we can track state during setup
    hass.data.setdefault(DOMAIN, {})
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    # Check if renewal was already scheduled by a previous setup (shouldn't happen, but safety check)
    already_scheduled = entry_data.get("_mqtt_renewal_scheduled", False)
    entry_data = {"_mqtt_renewal_scheduled": already_scheduled}  # Fresh dict, preserve flag

    # Initialize MQTT client object (connect happens below after hass.data is set)
    mqtt_client = None
    try:
        if PAHO_AVAILABLE:
            mqtt_creds = client.get_mqtt_credentials()
            if mqtt_creds.get("product_key") and mqtt_creds.get("device_name"):
                _LOGGER.info("HomGar [%s]: Initializing MQTT for real-time device updates", entry.title)

                # Call subscribeStatus to get fresh per-session virtual credentials
                # (these rotate each session — do not use stored ones)
                hubs = coordinator.data.get("hubs", []) if coordinator.data else []
                hids = entry.data.get(CONF_HIDS, [])
                sub_creds = {}
                if hubs and hids:
                    try:
                        sub_creds = await client.subscribe_status(hids[0], hubs)
                        _LOGGER.info(
                            "HomGar [%s]: subscribeStatus returned device=%s productKey=%s host=%s",
                            entry.title,
                            sub_creds.get("deviceName"),
                            sub_creds.get("productKey"),
                            sub_creds.get("mqttHostUrl"),
                        )
                    except Exception as sub_e:
                        _LOGGER.warning("HomGar [%s]: subscribeStatus failed, falling back to stored creds: %s", entry.title, sub_e)

                # Schedule MQTT renewal before expire timestamp
                expire_ms = sub_creds.get("expire") if sub_creds else None
                if expire_ms:
                    try:
                        expire_ts = int(expire_ms) / 1000.0
                        now = time.time()
                        renew_in = max(60, expire_ts - now - 60)
                        # Enforce minimum 30 min renewal interval to prevent excessive reloads
                        MIN_RENEWAL_INTERVAL = 1800  # 30 minutes
                        if renew_in < MIN_RENEWAL_INTERVAL:
                            _LOGGER.info(
                                "HomGar [%s]: MQTT renewal would be in %.0fs (too frequent), extending to %.0fs",
                                entry.title, renew_in, MIN_RENEWAL_INTERVAL
                            )
                            renew_in = MIN_RENEWAL_INTERVAL
                        actual_expire = datetime.fromtimestamp(expire_ts).isoformat()
                        _LOGGER.info(
                            "HomGar [%s]: MQTT subscription expires at %s (in %.0fs), scheduling renewal in %.0fs",
                            entry.title,
                            actual_expire,
                            expire_ts - now,
                            renew_in,
                        )
                        # Prevent duplicate renewal schedules on reload
                        if entry_data.get("_mqtt_renewal_scheduled"):
                            _LOGGER.info("HomGar [%s]: MQTT renewal already scheduled, skipping duplicate", entry.title)
                        else:
                            entry_data["_mqtt_renewal_scheduled"] = True
                            async def _renew_subscription(hass=hass, entry=entry):
                                _LOGGER.info("HomGar [%s]: Renewing MQTT subscription (pre-expire renewal)", entry.title)
                                await _async_renew_mqtt_subscription(hass, entry)
                            hass.loop.call_later(renew_in, lambda: hass.async_create_task(_renew_subscription()))
                    except Exception as renew_e:
                        _LOGGER.warning("HomGar [%s]: Failed to schedule MQTT renewal: %s", entry.title, renew_e)

                # Use fresh creds from subscribeStatus if available, else fall back to stored
                if sub_creds.get("deviceName") and sub_creds.get("deviceSecret"):
                    mqtt_host = sub_creds.get("mqttHostUrl", mqtt_creds["mqtt_host"])
                    if ":" in mqtt_host:
                        mqtt_host, mqtt_port_str = mqtt_host.rsplit(":", 1)
                        mqtt_port = int(mqtt_port_str)
                    else:
                        mqtt_port = 1883
                    connect_product_key = sub_creds["productKey"]
                    connect_device_name = sub_creds["deviceName"]
                    connect_device_secret = sub_creds["deviceSecret"]
                else:
                    mqtt_host = mqtt_creds["mqtt_host"]
                    mqtt_port = mqtt_creds.get("mqtt_port", 1883)
                    connect_product_key = mqtt_creds["product_key"]
                    connect_device_name = mqtt_creds["device_name"]
                    connect_device_secret = mqtt_creds["device_secret"]

                def on_mqtt_message(data: dict):
                    """Handle MQTT message safely from paho's background thread."""
                    hass.loop.call_soon_threadsafe(
                        lambda: hass.async_create_task(coordinator.handle_mqtt_update(data))
                    )

                mqtt_client = HomGarMQTTClient(
                    product_key=connect_product_key,
                    device_name=connect_device_name,
                    device_secret=connect_device_secret,
                    mqtt_host=mqtt_host,
                    on_message_callback=on_mqtt_message,
                    mqtt_port=mqtt_port,
                    entry_title=entry.title,
                )
            else:
                _LOGGER.warning("HomGar [%s]: MQTT credentials not available, using polling only", entry.title)
        else:
            _LOGGER.info("HomGar: paho-mqtt not installed, using polling only")
    except Exception as e:
        _LOGGER.warning("HomGar: MQTT initialization failed, using polling only: %s", e)
        mqtt_client = None

    # Store data before platform setup so sensor.py can access mqtt_client
    # entry_data was created earlier to track renewal schedule; add the main objects now
    entry_data["client"] = client
    entry_data["coordinator"] = coordinator
    entry_data["mqtt_client"] = mqtt_client
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry_data
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Connect MQTT after hass.data is set
    if mqtt_client is not None:
        try:
            await hass.async_add_executor_job(mqtt_client.connect)
            _LOGGER.info("HomGar [%s]: MQTT client connected successfully", entry.title)
        except Exception as e:
            _LOGGER.warning("HomGar [%s]: MQTT connect failed, using polling only: %s", entry.title, e)
            hass.data[DOMAIN][entry.entry_id]["mqtt_client"] = None

    # Set up services
    await async_setup_services(hass)

    _ensure_device_registry_parents(hass, entry, coordinator)

    _LOGGER.info("Setting up platforms: %s for entry: %s", PLATFORMS, entry.entry_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Completed platform setup for entry: %s", entry.entry_id)

    async def _async_finalize_device_layout() -> None:
        """Run post-setup registry/area work after platform entities exist.

        This must not block entry setup because live MQTT updates can keep the
        event loop active long enough that `async_block_till_done()` never
        settles during startup/reconfigure.
        """
        if entry.entry_id not in hass.data.get(DOMAIN, {}):
            return
        try:
            _LOGGER.info("HomGar [%s]: Finalizing device layout", entry.title)
            await async_merge_wifi_devices(hass, entry, coordinator)
            await async_rehome_multi_zone_entities(hass, entry, coordinator)
            _assign_devices_to_areas(hass, entry, coordinator)
            _LOGGER.info("HomGar [%s]: Device layout finalized", entry.title)
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("HomGar [%s]: Device layout finalization failed: %s", entry.title, ex, exc_info=True)

    async def _async_finalize_device_layout_later(_now) -> None:
        await _async_finalize_device_layout()

    # Run once shortly after setup returns so Home Assistant can finish
    # restoring entities before we move them between devices. A second delayed
    # pass caused transient empty child devices to linger during option flips.
    entry.async_on_unload(async_call_later(hass, 2, _async_finalize_device_layout_later))

    return True


def _fallback_hub_name(hub_info: dict) -> str:
    model = hub_info.get("model")
    return (
        hub_info.get("name")
        or hub_info.get("displayModel")
        or (model if model and model != "Unknown" else None)
        or "RainPoint Hub"
    )


def _ensure_device_registry_parents(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator,
) -> None:
    """Create parent devices before grouped child entities reference them."""
    data = coordinator.data
    if not data:
        return

    device_reg = dr.async_get(hass)
    hubs = data.get("hubs", [])
    if isinstance(hubs, dict):
        hubs = list(hubs.values())

    for hub_info in hubs:
        mid = hub_info.get("mid")
        if mid is None:
            continue
        device_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"rainpoint_hub_{mid}")},
            manufacturer="RainPoint",
            model=hub_info.get("model") or hub_info.get("displayModel") or "Unknown",
            name=_fallback_hub_name(hub_info),
            suggested_area=hub_info.get("homeName"),
        )

    if not entry.options.get(CONF_GROUP_MULTI_ZONE_DEVICES, False):
        return

    sensors = data.get("sensors", {})
    for sensor_info in sensors.values():
        mid = sensor_info.get("mid")
        addr = sensor_info.get("addr")
        model = sensor_info.get("model")
        if mid is None or addr is None or not model:
            continue
        if len(get_valve_ports(model)) <= 1 and len(get_switch_ports(model)) <= 1:
            continue
        if sensor_info.get("type_flag") == 1:
            continue

        device_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, controller_device_identifier(sensor_info))},
            manufacturer="RainPoint",
            model=model,
            name=sensor_info.get("sub_name") or f"Controller {addr}",
            suggested_area=sensor_info.get("home_name"),
            via_device=(DOMAIN, f"rainpoint_hub_{mid}"),
        )


def _assign_devices_to_areas(hass: HomeAssistant, entry: ConfigEntry, coordinator) -> None:
    """Create HA Areas for each home and assign all homgar devices to them."""
    from homeassistant.helpers import area_registry as ar, device_registry as dr

    data = coordinator.data
    if not data:
        return

    area_reg = ar.async_get(hass)
    device_reg = dr.async_get(hass)

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

        area = area_reg.async_get_area_by_name(home_name)
        if not area:
            area = area_reg.async_create(home_name)

        hub_device = device_reg.async_get_device(identifiers={(DOMAIN, f"rainpoint_hub_{mid}")})
        if hub_device:
            update: dict = {}
            if hub_device.area_id != area.id:
                update["area_id"] = area.id
            if not hub_device.name:
                update["name"] = _fallback_hub_name(hub_info)
            if not hub_device.model:
                update["model"] = hub_info.get("model") or hub_info.get("displayModel") or "Unknown"
            if update:
                device_reg.async_update_device(hub_device.id, **update)

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

        area = area_reg.async_get_area_by_name(home_name)
        if not area:
            area = area_reg.async_create(home_name)

        device = device_reg.async_get_device(identifiers={(DOMAIN, f"{mid}_{addr}")})
        if device and device.area_id != area.id:
            device_reg.async_update_device(device.id, area_id=area.id)

        model = sensor_info.get("model")
        if group_multi_zone and model and len(get_valve_ports(model)) > 1:
            for port in get_valve_ports(model):
                zone_device = device_reg.async_get_device(
                    identifiers={(DOMAIN, zone_device_identifier(mid, addr, port))}
                )
                if zone_device and zone_device.area_id != area.id:
                    device_reg.async_update_device(zone_device.id, area_id=area.id)


async def _async_renew_mqtt_subscription(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Renew MQTT subscription with fresh credentials without full integration reload.
    
    This avoids entities becoming 'unavailable' during renewal by:
    1. Keeping the coordinator and entities running
    2. Getting fresh MQTT credentials via subscribeStatus
    3. Disconnecting old MQTT client
    4. Creating and connecting new MQTT client with fresh credentials
    5. Updating hass.data with new client
    """
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    client = entry_data.get("client")
    coordinator = entry_data.get("coordinator")
    old_mqtt_client = entry_data.get("mqtt_client")
    
    if not client or not coordinator:
        _LOGGER.error("HomGar [%s]: Cannot renew MQTT - missing client or coordinator", entry.title)
        return False
    
    try:
        # Get fresh credentials via subscribeStatus
        hubs = coordinator.data.get("hubs", []) if coordinator.data else []
        hids = entry.data.get(CONF_HIDS, [])
        if not hubs or not hids:
            _LOGGER.warning("HomGar [%s]: Cannot renew MQTT - no hubs or hids", entry.title)
            return False
            
        sub_creds = await client.subscribe_status(hids[0], hubs)
        _LOGGER.info(
            "HomGar [%s]: MQTT renewal - subscribeStatus returned device=%s productKey=%s host=%s",
            entry.title,
            sub_creds.get("deviceName"),
            sub_creds.get("productKey"),
            sub_creds.get("mqttHostUrl"),
        )
        
        # Extract credentials
        if not sub_creds.get("deviceName") or not sub_creds.get("deviceSecret"):
            _LOGGER.error("HomGar [%s]: MQTT renewal - incomplete credentials from subscribeStatus", entry.title)
            return False
            
        mqtt_host = sub_creds.get("mqttHostUrl", "")
        if ":" in mqtt_host:
            mqtt_host, mqtt_port_str = mqtt_host.rsplit(":", 1)
            mqtt_port = int(mqtt_port_str)
        else:
            mqtt_port = 1883
            
        product_key = sub_creds["productKey"]
        device_name = sub_creds["deviceName"]
        device_secret = sub_creds["deviceSecret"]
        
        # Disconnect old client
        if old_mqtt_client:
            _LOGGER.info("HomGar [%s]: MQTT renewal - disconnecting old client", entry.title)
            await hass.async_add_executor_job(old_mqtt_client.disconnect)
        
        # Create new MQTT client with fresh credentials
        def on_mqtt_message(data: dict):
            """Handle MQTT message safely from paho's background thread."""
            hass.loop.call_soon_threadsafe(
                lambda: hass.async_create_task(coordinator.handle_mqtt_update(data))
            )
        
        new_mqtt_client = HomGarMQTTClient(
            product_key=product_key,
            device_name=device_name,
            device_secret=device_secret,
            mqtt_host=mqtt_host,
            on_message_callback=on_mqtt_message,
            mqtt_port=mqtt_port,
            entry_title=entry.title,
        )
        
        # Connect new client
        _LOGGER.info("HomGar [%s]: MQTT renewal - connecting new client", entry.title)
        connected = await hass.async_add_executor_job(new_mqtt_client.connect)
        if not connected:
            _LOGGER.error("HomGar [%s]: MQTT renewal - failed to connect new client", entry.title)
            return False
            
        # Update hass.data with new client
        entry_data["mqtt_client"] = new_mqtt_client
        entry_data["_mqtt_renewal_retry_count"] = 0
        _LOGGER.info("HomGar [%s]: MQTT renewal - successfully switched to new client", entry.title)
        
        # Schedule next renewal
        expire_ms = sub_creds.get("expire")
        if expire_ms:
            try:
                expire_ts = int(expire_ms) / 1000.0
                now = time.time()
                renew_in = max(60, expire_ts - now - 60)
                MIN_RENEWAL_INTERVAL = 1800  # 30 minutes
                if renew_in < MIN_RENEWAL_INTERVAL:
                    renew_in = MIN_RENEWAL_INTERVAL
                _LOGGER.info(
                    "HomGar [%s]: MQTT renewal complete - next renewal scheduled in %.0fs",
                    entry.title, renew_in
                )
                
                async def _schedule_next_renewal(hass=hass, entry=entry):
                    await _async_renew_mqtt_subscription(hass, entry)
                hass.loop.call_later(renew_in, lambda: hass.async_create_task(_schedule_next_renewal()))
            except Exception as sched_e:
                _LOGGER.warning("HomGar [%s]: MQTT renewal - failed to schedule next renewal: %s", entry.title, sched_e)
        
        return True
        
    except (asyncio.TimeoutError, ClientError) as e:
        retry_count = int(entry_data.get("_mqtt_renewal_retry_count", 0))
        retry_in = _MQTT_RENEWAL_BACKOFF_SECONDS[min(retry_count, len(_MQTT_RENEWAL_BACKOFF_SECONDS) - 1)]
        entry_data["_mqtt_renewal_retry_count"] = retry_count + 1
        _LOGGER.warning(
            "HomGar [%s]: MQTT renewal timed out: %s; retrying in %ss (attempt %s)",
            entry.title,
            e,
            retry_in,
            retry_count + 1,
        )

        async def _retry_renewal(hass=hass, entry=entry):
            await _async_renew_mqtt_subscription(hass, entry)

        hass.loop.call_later(retry_in, lambda: hass.async_create_task(_retry_renewal()))
        return False
    except Exception as e:
        _LOGGER.error("HomGar [%s]: MQTT renewal failed: %s", entry.title, e, exc_info=True)
        return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Disconnect MQTT client if present
        entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
        mqtt_client = entry_data.get("mqtt_client")
        if mqtt_client:
            _LOGGER.info("HomGar [%s]: Disconnecting MQTT client", entry.title)
            await hass.async_add_executor_job(mqtt_client.disconnect)
        
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_supports_reconfigure(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Return True if the integration supports reconfiguration."""
    return True


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up the HomGar services."""
    
    async def reload_service(call) -> None:
        """Service to reload the HomGar integration."""
        from homeassistant.components import persistent_notification
        
        entry_id = call.data.get("entry_id")
        
        # If no entry_id provided, reload all HomGar entries
        if not entry_id:
            entries = hass.config_entries.async_entries(DOMAIN)
            if not entries:
                _LOGGER.error("No HomGar entries found to reload")
                persistent_notification.async_create(
                    hass,
                    "No HomGar integrations found to reload",
                    title="HomGar Reload Failed",
                    notification_id="homgar_reload_error"
                )
                raise ValueError("No HomGar integrations found to reload")
            
            # Reload all entries
            success_count = 0
            for entry in entries:
                success = await async_reload_integration(hass, entry.entry_id)
                if success:
                    _LOGGER.info("HomGar integration '%s' reloaded successfully", entry.title)
                    success_count += 1
                else:
                    _LOGGER.error("Failed to reload HomGar integration '%s'", entry.title)
            
            message = f"Successfully reloaded {success_count} HomGar integration(s)"
            if success_count == len(entries):
                persistent_notification.async_create(
                    hass,
                    message,
                    title="HomGar Reload Complete",
                    notification_id="homgar_reload_success"
                )
                return {"message": message}
            else:
                error_msg = f"Only {success_count} of {len(entries)} integrations reloaded successfully"
                persistent_notification.async_create(
                    hass,
                    error_msg,
                    title="HomGar Reload Partial",
                    notification_id="homgar_reload_partial"
                )
                raise ValueError(error_msg)
        
        # Reload specific entry
        success = await async_reload_integration(hass, entry_id)
        if success:
            _LOGGER.info("HomGar integration reloaded successfully via service")
            persistent_notification.async_create(
                hass,
                "HomGar integration reloaded successfully",
                title="HomGar Reload Complete",
                notification_id="homgar_reload_success"
            )
            return {"message": "HomGar integration reloaded successfully"}
        else:
            _LOGGER.error("Failed to reload HomGar integration via service")
            persistent_notification.async_create(
                hass,
                "Failed to reload HomGar integration",
                title="HomGar Reload Failed",
                notification_id="homgar_reload_error"
            )
            raise ValueError("Failed to reload HomGar integration")
    
    # Register the service with optional entry_id
    hass.services.async_register(
        DOMAIN, 
        "reload", 
        reload_service, 
        schema=vol.Schema({
            vol.Optional("entry_id"): str,
        }),
        supports_response=True,
    )


async def async_get_diagnostic_info(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Return diagnostic information for this integration."""
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "domain": DOMAIN,
        "supports_reload": True,
    }


async def async_reload_integration(hass: HomeAssistant, entry_id: str) -> bool:
    """Reload the HomGar integration."""
    _LOGGER.info("Reloading HomGar integration: %s", entry_id)
    
    try:
        # Get the config entry
        entry = hass.config_entries.async_get_entry(entry_id)
        if not entry or entry.domain != DOMAIN:
            _LOGGER.error("Invalid entry for reload: %s", entry_id)
            return False
        
        # Reload the entry
        await hass.config_entries.async_reload(entry_id)
        _LOGGER.info("Successfully reloaded HomGar integration")
        return True
    except Exception as ex:
        _LOGGER.error("Failed to reload HomGar integration: %s", ex)
        return False
