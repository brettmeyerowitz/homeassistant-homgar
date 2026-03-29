"""
HomGar API client.

This module contains the main HomGarClient class for communicating
with the HomGar/RainPoint cloud API.
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import aiohttp

_LOGGER = logging.getLogger(__name__)


class HomGarApiError(Exception):
    pass


class HomGarClient:
    def __init__(self, area_code: str, email: str, password: str, session: aiohttp.ClientSession, app_type: str = "homgar"):
        self._area_code = area_code
        self._email = email
        self._password = password  # cleartext, HA will store
        self._session = session
        self._app_type = app_type
        
        # Import constants from const module
        from ..const import APP_CODE_MAPPING
        self._app_code = APP_CODE_MAPPING.get(app_type, "1")  # Default to homgar
        
        _LOGGER.info("HomGarClient initialized with app_type: %s, app_code: %s", self._app_type, self._app_code)

        self._token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: datetime | None = None

        # region host: you had region3; we can later make this configurable
        self._base_url = "https://region3.homgarus.com"

    # --- token state helpers ---

    def _auth_headers(self) -> dict:
        """Generate authentication headers for API calls."""
        if not self._token:
            raise HomGarApiError("Token not available")
        return {
            "auth": self._token, 
            "lang": "en", 
            "appCode": self._app_code,  # Use dynamic app_code based on user selection
            "version": "1.16.1065",
            "sceneType": "1"
        }

    def restore_tokens(self, data: dict) -> None:
        """Restore tokens from config entry data."""
        from ..const import CONF_TOKEN, CONF_REFRESH_TOKEN, CONF_TOKEN_EXPIRES_AT
        
        self._token = data.get(CONF_TOKEN)
        self._refresh_token = data.get(CONF_REFRESH_TOKEN)
        ts = data.get(CONF_TOKEN_EXPIRES_AT)
        try:
            self._token_expires_at = datetime.fromisoformat(ts) if ts else None
        except (ValueError, TypeError):
            self._token_expires_at = None

    def export_tokens(self) -> dict:
        """Export tokens for config entry storage."""
        from ..const import CONF_TOKEN, CONF_REFRESH_TOKEN, CONF_TOKEN_EXPIRES_AT
        
        return {
            CONF_TOKEN: self._token,
            CONF_REFRESH_TOKEN: self._refresh_token,
            CONF_TOKEN_EXPIRES_AT: self._token_expires_at.isoformat() if self._token_expires_at else None,
        }

    def is_token_valid(self) -> bool:
        """Check if current token is valid and not expired."""
        if not self._token:
            return False
        if not self._token_expires_at:
            return True  # No expiry info, assume valid
        return datetime.now(timezone.utc) < self._token_expires_at

    # --- authentication ---

    async def login(self) -> bool:
        """Perform login and store tokens."""
        url = f"{self._base_url}/app/login"
        payload = {
            "areaCode": self._area_code,
            "email": self._email,
            "password": self._password,
            "appCode": self._app_code,
        }
        async with self._session.post(url, json=payload) as resp:
            if resp.status != 200:
                _LOGGER.error("Login failed: %d %s", resp.status, await resp.text())
                return False
            data = await resp.json()
            if data.get("code") != 0:
                _LOGGER.error("Login API error: %s", data.get("msg"))
                return False
            self._token = data["data"]["token"]
            self._refresh_token = data["data"]["refreshToken"]
            # Set expiry to 7 days from now (typical for JWT)
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            _LOGGER.info("Login successful")
            return True

    async def refresh_token(self) -> bool:
        """Refresh access token using refresh token."""
        if not self._refresh_token:
            return await self.login()
        
        url = f"{self._base_url}/app/refreshToken"
        payload = {
            "refreshToken": self._refresh_token,
        }
        async with self._session.post(url, json=payload) as resp:
            if resp.status != 200:
                _LOGGER.warning("Token refresh failed: %d %s", resp.status, await resp.text())
                return await self.login()
            data = await resp.json()
            if data.get("code") != 0:
                _LOGGER.warning("Token refresh API error: %s", data.get("msg"))
                return await self.login()
            self._token = data["data"]["token"]
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            _LOGGER.info("Token refreshed")
            return True

    async def _ensure_auth(self) -> None:
        """Ensure we have a valid token, refreshing if necessary."""
        if not self.is_token_valid():
            if not await self.refresh_token():
                raise HomGarApiError("Authentication failed")

    # --- API calls ---

    async def get_homes(self) -> list:
        """Get list of homes for the user."""
        await self._ensure_auth()
        url = f"{self._base_url}/app/home/list"
        async with self._session.get(url, headers=self._auth_headers()) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"Failed to get homes: {resp.status}")
            data = await resp.json()
            if data.get("code") != 0:
                raise HomGarApiError(f"Homes API error: {data.get('msg')}")
            return data.get("data", [])

    async def get_devices(self, home_id: int) -> list:
        """Get devices for a specific home."""
        await self._ensure_auth()
        url = f"{self._base_url}/app/device/list"
        params = {"homeId": home_id}
        async with self._session.get(url, headers=self._auth_headers(), params=params) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"Failed to get devices: {resp.status}")
            data = await resp.json()
            if data.get("code") != 0:
                raise HomGarApiError(f"Devices API error: {data.get('msg')}")
            return data.get("data", [])

    async def get_devices_by_hid(self, hid: int) -> list[dict]:
        """Get devices by home ID (HID)."""
        await self._ensure_auth()
        url = f"{self._base_url}/app/device/getDeviceByHid"
        params = {"hid": hid}
        _LOGGER.debug("API call: get_devices_by_hid URL=%s params=%s", url, params)
        async with self._session.get(url, headers=self._auth_headers(), params=params) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"getDeviceByHid HTTP {resp.status}")
            data = await resp.json()
        _LOGGER.debug("API response: get_devices_by_hid data=%s", data)
        if data.get("code") != 0:
            raise HomGarApiError(f"getDeviceByHid failed: {data}")
        return data.get("data", [])

    async def get_multiple_device_status(self, devices: list) -> list[dict]:
        """Get status for multiple devices in one call."""
        await self._ensure_auth()
        url = f"{self._base_url}/app/device/multipleDeviceStatus"
        
        # Format devices array as expected by API
        device_list = []
        for device in devices:
            device_list.append({
                "deviceName": device.get("deviceName", ""),
                "mid": device["mid"],
                "productKey": device.get("productKey", "")
            })
        
        payload = {"devices": device_list}
        _LOGGER.debug("API call: get_multiple_device_status URL=%s payload=%s", url, payload)
        async with self._session.post(url, headers=self._auth_headers(), json=payload) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"Failed to get device status: {resp.status}")
            data = await resp.json()
        _LOGGER.debug("API response: get_multiple_device_status data=%s", data)
        if data.get("code") != 0:
            raise HomGarApiError(f"Device status API error: {data.get('msg')}")
        
        # Convert response format - API returns "status" but coordinator expects "subDeviceStatus"
        response_data = data.get("data", [])
        converted_data = []
        for device in response_data:
            converted_device = device.copy()
            if "status" in device:
                converted_device["subDeviceStatus"] = device["status"]
                # Remove the original "status" to avoid confusion
                del converted_device["status"]
            converted_data.append(converted_device)
        
        return converted_data

    async def get_device_status(self, mid: int) -> dict:
        """Get status for a single device by MID."""
        await self._ensure_auth()
        url = f"{self._base_url}/app/device/getDeviceStatus"
        params = {"mid": mid}
        _LOGGER.debug("API call: get_device_status URL=%s params=%s", url, params)
        async with self._session.get(url, headers=self._auth_headers(), params=params) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"getDeviceStatus HTTP {resp.status}")
            data = await resp.json()
        _LOGGER.debug("API response: get_device_status data=%s", data)
        if data.get("code") != 0:
            raise HomGarApiError(f"getDeviceStatus failed: {data}")
        return data.get("data", {})

    async def set_device_state(self, home_id: int, device_name: str, mid: int, product_key: str, state: dict) -> bool:
        """Set device state."""
        await self._ensure_auth()
        url = f"{self._base_url}/app/device/setDeviceStatus"
        payload = {
            "homeId": home_id,
            "deviceName": device_name,
            "mid": mid,
            "productKey": product_key,
            "status": state,
        }
        async with self._session.post(url, headers=self._auth_headers(), json=payload) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"Failed to set device state: {resp.status}")
            data = await resp.json()
            if data.get("code") != 0:
                raise HomGarApiError(f"Set device state API error: {data.get('msg')}")
            return True
