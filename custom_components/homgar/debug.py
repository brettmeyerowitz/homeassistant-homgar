"""Debug switch for submitting debug data to Cloudflare worker."""

import asyncio
import json
import logging
from datetime import datetime, timedelta

import aiohttp
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.persistent_notification import async_create
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import (
    CONF_DEBUG_LAST_SUBMISSION,
    DEBUG_SUBMISSION_INTERVAL,
    DEBUG_WORKER_URL,
    VERSION,
    debug_with_version,
)

_LOGGER = logging.getLogger(__name__)


class HomGarDebugSwitchEntity(SwitchEntity):
    """Switch for submitting HomGar debug data."""

    def __init__(self, hass: HomeAssistant, coordinator, integration_entry):
        """Initialize the debug switch."""
        self.hass = hass
        self.coordinator = coordinator
        self.integration_entry = integration_entry
        self._attr_is_on = False
        self._attr_unique_id = f"homgar_debug_{integration_entry.entry_id}"
        self._attr_name = "Submit Debug Data"
        self._attr_icon = "mdi:bug"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this entity."""
        return DeviceInfo(
            identifiers={("homgar", self.integration_entry.entry_id)},
            name="HomGar Integration",
            manufacturer="HomGar/RainPoint",
            model="Cloud Integration",
            sw_version=VERSION,
        )

    @property
    def available(self) -> bool:
        """Return if the switch is available."""
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs):
        """Submit debug data when switch is turned on."""
        _LOGGER.info(debug_with_version("Debug data submission initiated by user"))
        
        try:
            # Collect and submit debug data
            await self._submit_debug_data()
            
            # Show success notification
            self.hass.async_create_task(
                self._show_notification(
                    "✅ Debug data submitted successfully!\n\n"
                    "Thank you for helping improve the HomGar integration. "
                    "Your anonymous device data will help us discover new patterns "
                    "and improve decoder accuracy for everyone.",
                    "success"
                )
            )
            
            _LOGGER.info(debug_with_version("Debug data submission completed successfully"))
            
        except Exception as ex:
            _LOGGER.error(debug_with_version(f"Debug data submission failed: {ex}"))
            
            # Show error notification
            self.hass.async_create_task(
                self._show_notification(
                    "❌ Failed to submit debug data\n\n"
                    "Please try again later. If the problem persists, "
                    "check the integration logs for more details.",
                    "error"
                )
            )
        
        # Always turn off after submission (one-time action)
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn off the switch (no action needed)."""
        self._attr_is_on = False
        self.async_write_ha_state()

    async def _submit_debug_data(self):
        """Collect and submit debug data to Cloudflare worker."""
        # Collect data from all devices
        devices_data = await self._collect_device_data()
        
        # Submit each device separately
        successful_submissions = 0
        failed_submissions = 0
        
        for device_data in devices_data:
            try:
                # Submit to worker
                await self._post_to_worker(device_data)
                successful_submissions += 1
            except Exception as ex:
                _LOGGER.error(debug_with_version(f"Failed to submit device {device_data.get('device_model')}: {ex}"))
                failed_submissions += 1
        
        _LOGGER.info(debug_with_version(f"Debug submission complete: {successful_submissions} successful, {failed_submissions} failed"))
        
        if successful_submissions > 0:
            # Update last submission time
            await self._update_last_submission_time()

    async def _collect_device_data(self) -> list:
        """Collect data from all HomGar devices."""
        devices = []
        
        # Debug coordinator state
        _LOGGER.debug(debug_with_version(f"Coordinator available: {self.coordinator is not None}"))
        _LOGGER.debug(debug_with_version(f"Coordinator data type: {type(self.coordinator.data)}"))
        
        # Get device data from coordinator
        if hasattr(self.coordinator, 'data') and self.coordinator.data:
            _LOGGER.debug(debug_with_version(f"Coordinator data keys: {list(self.coordinator.data.keys())}"))
            
            # Device data is in the "sensors" dict
            sensors_data = self.coordinator.data.get("sensors", {})
            _LOGGER.debug(debug_with_version(f"Found {len(sensors_data)} sensors"))
            
            for device_key, device_info in sensors_data.items():
                _LOGGER.debug(debug_with_version(f"Processing device key: {device_key}, type: {type(device_info)}"))
                
                if isinstance(device_info, dict):
                    device_data = self._extract_device_data(device_info)
                    if device_data:
                        devices.append(device_data)
                        _LOGGER.debug(debug_with_version(f"Added device: {device_data.get('device_model')}"))
        else:
            _LOGGER.warning(debug_with_version("No coordinator data available"))
        
        _LOGGER.debug(debug_with_version(f"Collected data for {len(devices)} devices"))
        return devices

    def _extract_device_data(self, sensor_info: dict) -> dict:
        """Extract relevant data from a single device sensor."""
        try:
            # Sensor info structure: {hid, mid, addr, home_name, hub_name, sub_name, model, firmware_version, raw_status, data}
            if not sensor_info:
                return None
            
            # Extract sensor values from the data field
            device_data = sensor_info.get("data", {})
            if not device_data:
                _LOGGER.debug(debug_with_version(f"No data field for sensor {sensor_info.get('sub_name', 'unknown')}"))
                return None
            
            # Extract sensor values
            sensor_values = {}
            sensor_mappings = {
                "co2": "co2",
                "temperature": "temperature",
                "humidity": "humidity", 
                "moisture": "moisture_percent",
                "illuminance": "illuminance_lux",
                "flow": "flowcurrentused",
                "pressure": "pressure",
                "rain": "rain_last_24h_mm",
            }
            
            for key, value in device_data.items():
                if key in sensor_mappings and value is not None:
                    sensor_values[sensor_mappings[key]] = value
            
            # Get raw payload from raw_status
            raw_payload = None
            raw_status = sensor_info.get("raw_status", {})
            if isinstance(raw_status, dict):
                raw_payload = raw_status.get("value", "")
            
            return {
                "device_model": sensor_info.get("model"),
                "device_type": device_data.get("type"),
                "raw_payload": raw_payload,
                "decoded_values": sensor_values,
                "metadata": {
                    "rssi": device_data.get("rssi_dbm"),
                    "battery": device_data.get("battery_percent"),
                    "firmware": sensor_info.get("firmware_version"),
                    "device_timestamp": device_data.get("device_timestamp"),
                    "device_name": sensor_info.get("sub_name"),
                    "hub_name": sensor_info.get("hub_name"),
                },
                "integration_version": VERSION,
            }
            
        except Exception as ex:
            _LOGGER.warning(debug_with_version(f"Failed to extract device data: {ex}"))
            return None

    async def _post_to_worker(self, data: dict):
        """Post data to debug worker."""
        timeout = aiohttp.ClientTimeout(total=10)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {
                "User-Agent": f"HomeAssistant-HomGar/{VERSION}",
                "Content-Type": "application/json",
            }
            
            _LOGGER.debug(debug_with_version(f"Submitting to worker: {DEBUG_WORKER_URL}"))
            
            async with session.post(DEBUG_WORKER_URL, json=data, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Worker returned status {response.status}: {error_text}")
                
                result = await response.json()
                if result.get("status") != "success":
                    raise Exception(result.get("message", "Unknown error from worker"))
                
                _LOGGER.debug(debug_with_version(f"Worker response: {result}"))

    async def _update_last_submission_time(self):
        """Update the last submission time in config entry."""
        try:
            new_data = self.integration_entry.data.copy()
            new_data[CONF_DEBUG_LAST_SUBMISSION] = datetime.utcnow().isoformat()
            
            self.hass.config_entries.async_update_entry(
                self.integration_entry,
                data=new_data
            )
            
        except Exception as ex:
            _LOGGER.warning(debug_with_version(f"Failed to update last submission time: {ex}"))

    async def _show_notification(self, message: str, notification_type: str = "info"):
        """Show notification to user."""
        await async_create(
            self.hass,
            message,
            title="HomGar Debug Data",
            notification_id=f"homgar_debug_{notification_type}",
        )
