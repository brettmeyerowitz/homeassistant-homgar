import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, CONF_APP_TYPE
from .homgar_api import HomGarClient
from .mqtt_client import HomGarMQTTClient, PAHO_AVAILABLE

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "valve", "number", "switch"]


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

    # Simple: one coordinator per config entry
    from .coordinator import HomGarCoordinator

    coordinator = HomGarCoordinator(hass, client, entry)

    await coordinator.async_config_entry_first_refresh()

    # Initialize MQTT for real-time valve updates (optional, graceful fallback)
    mqtt_client = None
    try:
        if PAHO_AVAILABLE:
            mqtt_creds = client.get_mqtt_credentials()
            if mqtt_creds.get("product_key") and mqtt_creds.get("device_name"):
                _LOGGER.info("HomGar: Initializing MQTT for real-time valve updates")
                
                def on_mqtt_message(data: dict):
                    """Handle MQTT message in async context."""
                    hass.async_create_task(coordinator.handle_mqtt_update(data))
                
                mqtt_client = HomGarMQTTClient(
                    product_key=mqtt_creds["product_key"],
                    device_name=mqtt_creds["device_name"],
                    device_secret=mqtt_creds["device_secret"],
                    mqtt_host=mqtt_creds["mqtt_host"],
                    on_message_callback=on_mqtt_message,
                    mqtt_port=mqtt_creds.get("mqtt_port", 1883),
                )
                
                # Connect MQTT in background
                await hass.async_add_executor_job(mqtt_client.connect)
                _LOGGER.info("HomGar: MQTT client connected successfully")
            else:
                _LOGGER.warning("HomGar: MQTT credentials not available, using polling only")
        else:
            _LOGGER.info("HomGar: paho-mqtt not installed, using polling only")
    except Exception as e:
        _LOGGER.warning("HomGar: MQTT initialization failed, using polling only: %s", e)
        mqtt_client = None

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "mqtt_client": mqtt_client,
    }

    # Set up services
    await async_setup_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Disconnect MQTT client if present
        entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
        mqtt_client = entry_data.get("mqtt_client")
        if mqtt_client:
            _LOGGER.info("HomGar: Disconnecting MQTT client")
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
    
    async def reauthenticate_service(call) -> None:
        """Service to force re-authentication after mobile app login."""
        from homeassistant.components import persistent_notification
        
        entry_id = call.data.get("entry_id")
        
        if not entry_id:
            _LOGGER.error("No entry_id provided for re-authentication")
            persistent_notification.async_create(
                hass,
                "Please provide an entry_id for re-authentication",
                title="HomGar Re-authentication Failed",
                notification_id="homgar_reauth_error"
            )
            raise ValueError("entry_id is required for re-authentication")
        
        # Get the config entry
        entry = hass.config_entries.async_get_entry(entry_id)
        if not entry or entry.domain != DOMAIN:
            _LOGGER.error("Invalid entry for re-authentication: %s", entry_id)
            persistent_notification.async_create(
                hass,
                f"Invalid HomGar entry: {entry_id}",
                title="HomGar Re-authentication Failed",
                notification_id="homgar_reauth_error"
            )
            raise ValueError(f"Invalid entry_id: {entry_id}")
        
        # Get the entry data and client
        entry_data = hass.data[DOMAIN].get(entry_id, {})
        client = entry_data.get("client")
        coordinator = entry_data.get("coordinator")
        
        if not client:
            _LOGGER.error("No client found for entry: %s", entry_id)
            persistent_notification.async_create(
                hass,
                "No client found for this integration",
                title="HomGar Re-authentication Failed",
                notification_id="homgar_reauth_error"
            )
            raise ValueError("No client available")
        
        try:
            # Force re-authentication by clearing tokens and logging in again
            _LOGGER.info("Forcing re-authentication for HomGar entry: %s", entry_id)
            
            # Clear current tokens
            client._token = None
            client._refresh_token = None
            client._token_expires_at = None
            
            # Force login to get new tokens
            success = await client.login()
            if success:
                # Update the config entry with new tokens
                new_tokens = client.export_tokens()
                new_data = dict(entry.data)
                new_data.update(new_tokens)
                
                # Update the entry data
                hass.config_entries.async_update_entry(entry, data=new_data)
                
                # Force coordinator refresh to test new tokens
                if coordinator:
                    await coordinator.async_request_refresh()
                
                _LOGGER.info("HomGar re-authentication successful for entry: %s", entry_id)
                persistent_notification.async_create(
                    hass,
                    "HomGar integration re-authenticated successfully. You can now use your mobile app login.",
                    title="HomGar Re-authentication Complete",
                    notification_id="homgar_reauth_success"
                )
                return {"message": "Re-authentication successful"}
            else:
                _LOGGER.error("HomGar re-authentication failed for entry: %s", entry_id)
                persistent_notification.async_create(
                    hass,
                    "Failed to re-authenticate HomGar. Please check your credentials.",
                    title="HomGar Re-authentication Failed",
                    notification_id="homgar_reauth_error"
                )
                raise ValueError("Re-authentication failed")
                
        except Exception as ex:
            _LOGGER.error("Error during HomGar re-authentication: %s", ex)
            persistent_notification.async_create(
                hass,
                f"Re-authentication error: {str(ex)}",
                title="HomGar Re-authentication Failed",
                notification_id="homgar_reauth_error"
            )
            raise ValueError(f"Re-authentication error: {str(ex)}")
    
    # Register the reload service
    hass.services.async_register(
        DOMAIN, 
        "reload", 
        reload_service, 
        schema=vol.Schema({
            vol.Optional("entry_id"): str,
        }),
        supports_response=True,
    )
    
    # Register the re-authentication service
    hass.services.async_register(
        DOMAIN, 
        "reauthenticate", 
        reauthenticate_service, 
        schema=vol.Schema({
            vol.Required("entry_id"): str,
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