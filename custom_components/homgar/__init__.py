import logging
import time
from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, CONF_APP_TYPE, CONF_HIDS
from .coordinator import HomGarCoordinator
from .decoder import _MODELS  # noqa: F401 — imported here to trigger eager file load in executor
from .homgar_api import HomGarClient
from .mqtt_client import HomGarMQTTClient, PAHO_AVAILABLE

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "valve", "number"]


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
        await client.login()

    coordinator = HomGarCoordinator(hass, client, entry)

    await coordinator.async_config_entry_first_refresh()

    # Persist MQTT credentials to config entry if freshly obtained via login
    mqtt_creds = client.get_mqtt_credentials()
    if mqtt_creds.get("product_key") and not entry.data.get(CONF_MQTT_PRODUCT_KEY):
        hass.config_entries.async_update_entry(entry, data={**entry.data, **client.export_tokens()})

    # Migrate v1->v2 unique_ids before platform setup so renamed IDs don't
    # collide with freshly registered entities
    from .migrate import async_migrate_unique_ids, async_merge_wifi_devices
    await async_migrate_unique_ids(hass, entry, coordinator)

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
                        renew_in = max(60, expire_ts - time.time() - 60)
                        _LOGGER.info(
                            "HomGar [%s]: MQTT subscription expires in %.0fs, scheduling renewal in %.0fs",
                            entry.title,
                            expire_ts - time.time(),
                            renew_in,
                        )
                        async def _renew_subscription(hass=hass, entry=entry):
                            _LOGGER.info("HomGar [%s]: Renewing MQTT subscription (pre-expire renewal)", entry.title)
                            await async_reload_entry(hass, entry)
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
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "mqtt_client": mqtt_client,
    }

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

    _LOGGER.info("Setting up platforms: %s for entry: %s", PLATFORMS, entry.entry_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Completed platform setup for entry: %s", entry.entry_id)

    # Merge WiFi self-contained devices after platform setup (hub device must exist first)
    await async_merge_wifi_devices(hass, entry, coordinator)

    # Assign devices to HA Areas based on home name — runs every startup so
    # areas are kept in sync even when suggested_area hint was missed
    _assign_devices_to_areas(hass, entry, coordinator)

    return True


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
        if hub_device and hub_device.area_id != area.id:
            device_reg.async_update_device(hub_device.id, area_id=area.id)

    sensors = data.get("sensors", {})
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
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


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