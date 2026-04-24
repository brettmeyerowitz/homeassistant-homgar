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
        self._mqtt_credentials: dict = {}

        # region host: you had region3; we can later make this configurable
        self._base_url = "https://region3.homgarus.com"
        
        # Generate a random deviceId for this session
        self._device_id = self._generate_device_id()

    def _generate_device_id(self) -> str:
        """Generate a deterministic deviceId for authentication."""
        # Device ID is required; generate deterministic 16 bytes hex from email+areaCode
        return hashlib.md5(f"{self._email}{self._area_code}".encode("utf-8")).hexdigest()

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
        from ..const import CONF_TOKEN, CONF_REFRESH_TOKEN, CONF_TOKEN_EXPIRES_AT, \
            CONF_MQTT_PRODUCT_KEY, CONF_MQTT_DEVICE_NAME, CONF_MQTT_DEVICE_SECRET, CONF_MQTT_HOST
        
        self._token = data.get(CONF_TOKEN)
        self._refresh_token = data.get(CONF_REFRESH_TOKEN)
        ts = data.get(CONF_TOKEN_EXPIRES_AT)
        try:
            self._token_expires_at = datetime.fromisoformat(ts) if ts else None
        except (ValueError, TypeError):
            self._token_expires_at = None

        if data.get(CONF_MQTT_PRODUCT_KEY) and data.get(CONF_MQTT_DEVICE_NAME):
            self._mqtt_credentials = {
                "product_key": data[CONF_MQTT_PRODUCT_KEY],
                "device_name": data[CONF_MQTT_DEVICE_NAME],
                "device_secret": data.get(CONF_MQTT_DEVICE_SECRET, ""),
                "mqtt_host": data.get(CONF_MQTT_HOST, ""),
                "mqtt_port": 1883,
            }

    def get_mqtt_credentials(self) -> dict:
        """Get MQTT credentials for real-time updates."""
        return self._mqtt_credentials.copy()

    def export_tokens(self) -> dict:
        """Export tokens for config entry storage."""
        from ..const import CONF_TOKEN, CONF_REFRESH_TOKEN, CONF_TOKEN_EXPIRES_AT, \
            CONF_MQTT_PRODUCT_KEY, CONF_MQTT_DEVICE_NAME, CONF_MQTT_DEVICE_SECRET, CONF_MQTT_HOST
        
        result = {
            CONF_TOKEN: self._token,
            CONF_REFRESH_TOKEN: self._refresh_token,
            CONF_TOKEN_EXPIRES_AT: self._token_expires_at.isoformat() if self._token_expires_at else None,
        }
        if self._mqtt_credentials.get("product_key"):
            result[CONF_MQTT_PRODUCT_KEY] = self._mqtt_credentials["product_key"]
            result[CONF_MQTT_DEVICE_NAME] = self._mqtt_credentials["device_name"]
            result[CONF_MQTT_DEVICE_SECRET] = self._mqtt_credentials.get("device_secret", "")
            result[CONF_MQTT_HOST] = self._mqtt_credentials.get("mqtt_host", "")
        return result

    def is_token_valid(self) -> bool:
        """Check if current token is valid and not expired."""
        if not self._token:
            return False
        if not self._token_expires_at:
            return True  # No expiry info, assume valid
        return datetime.now(timezone.utc) < self._token_expires_at

    # --- authentication ---

    async def ensure_logged_in(self) -> None:
        """Ensure we have a valid token, logging in if necessary."""
        if not self.is_token_valid():
            success = await self.login()
            if not success:
                raise HomGarApiError("Failed to login")

    async def login(self) -> bool:
        """Perform login and store tokens."""
        url = f"{self._base_url}/auth/basic/app/login"
        
        # Hash password with MD5 as required by the API
        password_md5 = hashlib.md5(self._password.encode()).hexdigest()
        
        payload = {
            "areaCode": self._area_code,
            "phoneOrEmail": self._email,
            "password": password_md5,
            "deviceId": self._device_id,
        }
        
        headers = {
            "Content-Type": "application/json",
            "lang": "en",
            "appCode": self._app_code,
        }
        
        _LOGGER.debug("API call: login URL=%s appCode=%s deviceId=%s", url, self._app_code, self._device_id)
        
        async with self._session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                _LOGGER.error("Login failed: %d %s", resp.status, await resp.text())
                return False
            data = await resp.json()
            _LOGGER.debug("API response: login data=%s", data)
            
            if data.get("code") != 0:
                _LOGGER.error("Login API error: %s", data.get("msg"))
                return False
                
            d = data["data"]
            self._token = d["token"]
            self._refresh_token = d.get("refreshToken")
            
            # Extract MQTT credentials from user data (only if present)
            user_data = d.get("user", {})
            mqtt_host = d.get("mqttHostUrl", "")
            _LOGGER.debug("HomGar login response keys: top=%s, user_keys=%s, mqtt_host=%s, productKey=%s, deviceName=%s",
                list(d.keys()), list(user_data.keys()) if user_data else [], mqtt_host,
                user_data.get("productKey"), user_data.get("deviceName"))
            
            if user_data.get("productKey") and user_data.get("deviceName") and mqtt_host:
                self._mqtt_credentials = {
                    "product_key": user_data.get("productKey"),
                    "device_name": user_data.get("deviceName"),
                    "device_secret": user_data.get("deviceSecret", ""),
                    "mqtt_host": mqtt_host.replace(":1883", ""),  # Remove port if present
                    "mqtt_port": 1883,
                }
                
                _LOGGER.info(
                    "HomGar MQTT credentials extracted: product_key=%s device_name=%s mqtt_host=%s",
                    self._mqtt_credentials.get("product_key"),
                    self._mqtt_credentials.get("device_name"),
                    self._mqtt_credentials.get("mqtt_host"),
                )
            else:
                _LOGGER.debug("HomGar MQTT credentials not present in login response")
            
            # Use server's tokenExpired field instead of hardcoded 7 days
            token_expired_secs = d.get("tokenExpired", 0)
            ts_server = data.get("ts")  # ms since epoch
            
            if ts_server:
                base = datetime.fromtimestamp(ts_server / 1000, tz=timezone.utc)
            else:
                base = datetime.now(timezone.utc)
                
            self._token_expires_at = base + timedelta(seconds=token_expired_secs)
            
            _LOGGER.info("HomGar login successful; token expires in %s seconds", token_expired_secs)
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

    async def _reauth(self) -> None:
        """Force a fresh login, invalidating the current token."""
        _LOGGER.info("HomGar: token rejected by server, forcing fresh login")
        self._token = None
        self._token_expires_at = None
        if not await self.login():
            raise HomGarApiError("Re-authentication failed")

    # --- API calls ---

    async def list_homes(self) -> list[dict]:
        """Get list of homes for the user."""
        await self.ensure_logged_in()
        url = f"{self._base_url}/app/member/appHome/list"
        _LOGGER.debug("API call: list_homes URL=%s", url)
        
        async with self._session.get(url, headers=self._auth_headers()) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"list_homes HTTP {resp.status}")
            data = await resp.json()
            _LOGGER.debug("API response: list_homes data=%s", data)
        if data.get("code") in (1001, 1004):
            await self._reauth()
            async with self._session.get(url, headers=self._auth_headers()) as resp2:
                data = await resp2.json()
        if data.get("code") != 0:
            raise HomGarApiError(f"list_homes failed: {data}")
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
        if data.get("code") in (1001, 1004):
            await self._reauth()
            async with self._session.get(url, headers=self._auth_headers(), params=params) as resp2:
                data = await resp2.json()
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
        if data.get("code") in (1001, 1004):
            await self._reauth()
            async with self._session.post(url, headers=self._auth_headers(), json=payload) as resp2:
                data = await resp2.json()
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

    async def subscribe_status(self, hid: int, hubs: list[dict]) -> dict:
        """Call /app/device/subscribeStatus to get fresh per-session MQTT credentials.

        Returns the full response data dict including:
          deviceName, productKey, deviceSecret, mqttHostUrl (physical hub observer session)
        """
        await self._ensure_auth()
        url = f"{self._base_url}/app/device/subscribeStatus"

        import uuid as _uuid
        subscribe_list = [
            {"deviceName": h.get("deviceName", ""), "mid": h["mid"], "productKey": h.get("productKey", "")}
            for h in hubs
        ]
        payload = {
            "hid": str(hid),
            "hidList": [str(hid)],
            "subscribe": subscribe_list,
            "unsubscribe": [],
            "userInfo": {
                "deviceName": self._mqtt_credentials.get("device_name", ""),
                "deviceType": 1,
                "notice": 0,
                "productKey": self._mqtt_credentials.get("product_key", ""),
                "pushId": _uuid.uuid4().hex,
            },
        }
        _LOGGER.debug("API call: subscribe_status URL=%s payload=%s", url, payload)
        async with self._session.post(url, headers=self._auth_headers(), json=payload) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"subscribeStatus HTTP {resp.status}")
            data = await resp.json()
        _LOGGER.debug("API response: subscribe_status data=%s", data)
        if data.get("code") != 0:
            raise HomGarApiError(f"subscribeStatus failed: {data}")
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

    async def get_product_models(self, version: int = 0) -> list[dict]:
        """Get full product model list from API.
        
        Returns list of all device models supported by the platform.
        """
        await self.ensure_logged_in()
        url = f"{self._base_url}/app/common/core/productModel"
        params = {"version": version}
        
        _LOGGER.debug("API call: get_product_models URL=%s params=%s", url, params)
        async with self._session.get(url, headers=self._auth_headers(), params=params) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"2026-04-10 21:22:21.337 DEBUG (MainThread) [custom_components.homgar.api.client] API call: get_product_models URL=https://region3.homgarus.com/app/common/core/productModel params={'version': 0} HTTP {resp.status}")
            data = await resp.json()
        
        _LOGGER.warning("API response: get_product_models received, code=%s", data.get('code'))
        
        # Log full response to file for inspection
        try:
            with open('/tmp/product_models.json', 'w') as f:
                import json
                json.dump(data, f, indent=2)
            _LOGGER.warning("Full product models written to /tmp/product_models.json")
        except Exception as e:
            _LOGGER.warning("Could not write product models to file: %s", e)
        
        # Handle unexpected response format
        if not isinstance(data, dict):
            _LOGGER.warning("Unexpected product_models response type: %s", type(data))
            return []
        
        if data.get("code") != 0:
            _LOGGER.warning("get_product_models API error: %s", data)
            return []
        
        # Extract models from data['data']['models'] structure
        data_section = data.get("data", {})
        if isinstance(data_section, dict):
            result = data_section.get("models", [])
        else:
            result = []
        
        _LOGGER.warning("Extracted %d product models", len(result))
        
        if not isinstance(result, list):
            _LOGGER.warning("Unexpected product_models data type: %s", type(result))
            return []
        
        return result

    def _extract_control_response_state(self, data: dict) -> str | None:
        """Extract an optional state payload from a control endpoint response."""
        response_data = data.get("data")
        if isinstance(response_data, dict):
            state = response_data.get("state")
            if isinstance(state, str):
                return state
        return None

    def _encode_control_work_mode_dp_param(self, mode: int, duration: int) -> str:
        """Encode BLE valve runtime as the little-endian hex blob used by the app."""
        if mode == 0:
            return "00000000"
        duration = max(0, int(duration))
        return duration.to_bytes(4, byteorder="little", signed=False).hex()

    def _build_control_work_mode_dp_payload(
        self,
        mid: int,
        addr: int,
        device_name: str,
        product_key: str,
        port: int,
        mode: int,
        duration: int,
        dp_code: int = 1,
    ) -> dict:
        """Build the BLE valve control payload used by the RainPoint app."""
        return {
            "mid": str(mid),
            "productKey": product_key,
            "deviceName": device_name,
            "mode": mode,
            "addr": addr,
            "port": port,
            "param": self._encode_control_work_mode_dp_param(mode, duration),
            "dpCode": dp_code,
        }

    async def control_work_mode(
        self,
        mid: int,
        addr: int,
        device_name: str,
        product_key: str,
        port: int,
        mode: int,
        duration: int,
        hid: int | None = None,
    ) -> str | None:
        """
        Control a valve zone via the legacy RF-oriented controlWorkMode endpoint.
        """
        await self.ensure_logged_in()
        url = f"{self._base_url}/app/device/controlWorkMode"
        payload = {
            "deviceName": device_name,
            "productKey": product_key,
            "mid": str(mid),
            "addr": addr,
            "port": port,
            "mode": mode,
            "duration": duration,
            "param": "",
        }
        if hid is not None:
            payload["hid"] = str(hid)
        _LOGGER.debug("API call: control_work_mode URL=%s payload=%s", url, payload)

        async with self._session.post(url, json=payload, headers=self._auth_headers()) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"controlWorkMode HTTP {resp.status}")
            data = await resp.json()

        _LOGGER.debug("API response: control_work_mode data=%s", data)

        code = data.get("code")
        if code == 4:
            _LOGGER.warning(
                "controlWorkMode returned code 4 (busy/already in state), treating as non-fatal: %s",
                data,
            )
            return self._extract_control_response_state(data)
        if code != 0:
            raise HomGarApiError(f"controlWorkMode failed: code={code} msg={data.get('msg')}")
        return self._extract_control_response_state(data)

    async def control_work_mode_dp(
        self,
        mid: int,
        addr: int,
        device_name: str,
        product_key: str,
        port: int,
        mode: int,
        duration: int,
        hid: int | None = None,
        dp_code: int = 1,
    ) -> str | None:
        """
        Control a BLE-backed valve zone via the app's controlWorkModeDP endpoint.
        """
        await self.ensure_logged_in()
        url = f"{self._base_url}/app/device/controlWorkModeDP"
        payload = self._build_control_work_mode_dp_payload(
            mid=mid,
            addr=addr,
            device_name=device_name,
            product_key=product_key,
            port=port,
            mode=mode,
            duration=duration,
            dp_code=dp_code,
        )
        headers = self._auth_headers()
        if hid is not None:
            headers["hid"] = str(hid)

        _LOGGER.debug("API call: control_work_mode_dp URL=%s payload=%s", url, payload)

        async with self._session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"controlWorkModeDP HTTP {resp.status}")
            data = await resp.json()

        _LOGGER.debug("API response: control_work_mode_dp data=%s", data)

        code = data.get("code")
        if code == 4:
            _LOGGER.warning(
                "controlWorkModeDP returned code 4 (busy/already in state), treating as non-fatal: %s",
                data,
            )
            return self._extract_control_response_state(data)
        if code != 0:
            raise HomGarApiError(f"controlWorkModeDP failed: code={code} msg={data.get('msg')}")
        return self._extract_control_response_state(data)
