# DP IDs for valve hub zone state and duration (confirmed via payload capture)
# Zone N state DP   = _DP_HUB_STATE + N  (0x19 = zone 1, 0x1A = zone 2, ...)
# Zone N duration DP = _DP_BASE_DURATION + N (0x25 = zone 1, 0x26 = zone 2, ...)
_DP_HUB_STATE = 0x18
_DP_BASE_DURATION = 0x24  # zone N duration DP = 0x24 + N

# Decoder for HWS019WRF-V2 (Display Hub) CSV/semicolon payload
def decode_hws019wrf_v2(raw: str) -> dict:
    """
    Decode HWS019WRF-V2 (Display Hub) CSV/semicolon payload.
    Example: '1,0,1;788(788/777/1),68(68/64/1),P=9685(9684/9684/1),'
    """
    _LOGGER.debug("decode_hws019wrf_v2 called with raw: %r", raw)
    try:
        parts = raw.split(';')
        # First part: status flags (e.g., '1,0,1')
        flags = [int(x) for x in parts[0].split(',') if x.strip().isdigit()]
        readings = {}
        if len(parts) > 1:
            for item in parts[1].split(','):
                item = item.strip()
                if not item:
                    continue
                if '(' in item:
                    key, val = item.split('(', 1)
                    readings[key.strip()] = val.strip(')')
                elif '=' in item:
                    key, val = item.split('=', 1)
                    readings[key.strip()] = val.strip()
        result = {
            "type": "hws019wrf_v2",
            "flags": flags,
            "readings": readings,
            "raw": raw,
        }
        _LOGGER.debug("decode_hws019wrf_v2 result: %r", result)
        return result
    except Exception as ex:
        _LOGGER.warning("Failed to decode HWS019WRF-V2 payload: %s (raw: %r)", ex, raw)
        return {"type": "hws019wrf_v2", "raw": raw, "error": str(ex)}
import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import aiohttp

from .const import (
    CONF_AREA_CODE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_APP_TYPE,
    APP_CODE_MAPPING,
)

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
        self._app_code = APP_CODE_MAPPING.get(app_type, "1")  # Default to homgar
        
        _LOGGER.info("HomGarClient initialized with app_type: %s, app_code: %s", self._app_type, self._app_code)

        self._token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: datetime | None = None

        # region host: you had region3; we can later make this configurable
        self._base_url = "https://region3.homgarus.com"

    # --- token state helpers ---

    def restore_tokens(self, data: dict) -> None:
        """Restore tokens from config entry data."""
        self._token = data.get(CONF_TOKEN)
        self._refresh_token = data.get(CONF_REFRESH_TOKEN)
        ts = data.get(CONF_TOKEN_EXPIRES_AT)
        if ts is not None:
            self._token_expires_at = datetime.fromtimestamp(ts, tz=timezone.utc)

    def export_tokens(self) -> dict:
        """Export current token state as a dict for config entry updates."""
        return {
            CONF_TOKEN: self._token,
            CONF_REFRESH_TOKEN: self._refresh_token,
            CONF_TOKEN_EXPIRES_AT: int(self._token_expires_at.timestamp()) if self._token_expires_at else None,
        }

    def _token_valid(self) -> bool:
        if not self._token or not self._token_expires_at:
            return False
        # refresh a little before expiry
        return datetime.now(timezone.utc) < (self._token_expires_at - timedelta(minutes=5))

    # --- login / auth ---

    async def ensure_logged_in(self) -> None:
        if self._token_valid():
            return
        await self._login()

    async def _login(self) -> None:
        """Login with areaCode/email/password and store token info."""
        url = f"{self._base_url}/auth/basic/app/login"

        # Client-side MD5 hashing as per app/Postman flow
        md5 = hashlib.md5(self._password.encode("utf-8")).hexdigest()

        # Device ID is required; generate random 16 bytes hex
        device_id = hashlib.md5(f"{self._email}{self._area_code}".encode("utf-8")).hexdigest()

        payload = {
            "areaCode": self._area_code,
            "phoneOrEmail": self._email,
            "password": md5,
            "deviceId": device_id,
        }

        _LOGGER.debug("HomGar login request for %s with appCode=%s", self._email, self._app_code)

        async with self._session.post(url, json=payload, headers={"Content-Type": "application/json", "lang": "en", "appCode": self._app_code}) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"Login HTTP {resp.status}")
            data = await resp.json()

        if data.get("code") != 0 or "data" not in data:
            raise HomGarApiError(f"Login failed: {data}")

        d = data["data"]
        self._token = d["token"]
        self._refresh_token = d.get("refreshToken")
        token_expired_secs = d.get("tokenExpired", 0)
        ts_server = data.get("ts")  # ms since epoch
        if ts_server:
            base = datetime.fromtimestamp(ts_server / 1000, tz=timezone.utc)
        else:
            base = datetime.now(timezone.utc)
        self._token_expires_at = base + timedelta(seconds=token_expired_secs)

        _LOGGER.info("HomGar login successful; token expires in %s seconds", token_expired_secs)

    def _auth_headers(self) -> dict:
        if not self._token:
            raise HomGarApiError("Token not available")
        return {
            "auth": self._token, 
            "lang": "en", 
            "appCode": self._app_code,  # Use dynamic app_code based on user selection
            "version": "1.16.1065",
            "sceneType": "1"
        }

    # --- API calls ---

    async def list_homes(self) -> list[dict]:
        await self.ensure_logged_in()
        url = f"{self._base_url}/app/member/appHome/list"
        _LOGGER.debug("API call: list_homes URL=%s", url)
        async with self._session.get(url, headers=self._auth_headers()) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"list_homes HTTP {resp.status}")
            data = await resp.json()
        _LOGGER.debug("API response: list_homes data=%s", data)
        if data.get("code") != 0:
            raise HomGarApiError(f"list_homes failed: {data}")
        return data.get("data", [])

    async def get_devices_by_hid(self, hid: int) -> list[dict]:
        await self.ensure_logged_in()
        url = f"{self._base_url}/app/device/getDeviceByHid"
        params = {"hid": hid}
        _LOGGER.debug("API call: get_devices_by_hid URL=%s params=%s", url, params)
        async with self._session.get(url, params=params, headers=self._auth_headers()) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"getDeviceByHid HTTP {resp.status}")
            data = await resp.json()
        _LOGGER.debug("API response: get_devices_by_hid data=%s", data)
        if data.get("code") != 0:
            raise HomGarApiError(f"getDeviceByHid failed: {data}")
        return data.get("data", [])

    async def get_device_status(self, mid: int) -> dict:
        await self.ensure_logged_in()
        url = f"{self._base_url}/app/device/getDeviceStatus"
        params = {"mid": mid}
        _LOGGER.debug("API call: get_device_status URL=%s params=%s", url, params)
        async with self._session.get(url, params=params, headers=self._auth_headers()) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"getDeviceStatus HTTP {resp.status}")
            data = await resp.json()
        _LOGGER.debug("API response: get_device_status data=%s", data)
        if data.get("code") != 0:
            raise HomGarApiError(f"getDeviceStatus failed: {data}")
        return data.get("data", {})

    async def get_multiple_device_status(self, devices: list[dict]) -> list[dict]:
        """Get status for multiple devices in one API call (more efficient)."""
        await self.ensure_logged_in()
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
        async with self._session.post(url, json=payload, headers=self._auth_headers()) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"multipleDeviceStatus HTTP {resp.status}")
            data = await resp.json()
        _LOGGER.debug("API response: get_multiple_device_status data=%s", data)
        if data.get("code") != 0:
            raise HomGarApiError(f"multipleDeviceStatus failed: {data}")
        
        # Convert response format to match individual device status format
        # Response has: [{"propVer": X, "status": [...], "mid": Y, "iotId": Z}, ...]
        # We need: [{"mid": Y, "subDeviceStatus": [...]}]
        converted_data = []
        for device_data in data.get("data", []):
            converted_data.append({
                "mid": device_data["mid"],
                "subDeviceStatus": device_data.get("status", [])
            })
        
        return converted_data
    
    # --- Payload decoding helpers ---

def _parse_homgar_payload(raw: str) -> list[int]:
    """Turn '10#E1...' or '11#...' (N#hex) into [0-255] bytes list."""
    if not raw or "#" not in raw:
        raise ValueError(f"Unexpected payload format: {raw!r}")
    hex_str = raw.split("#", 1)[1]
    if len(hex_str) % 2 != 0:
        raise ValueError(f"Hex payload length must be even: {hex_str}")
    out: list[int] = []
    for i in range(0, len(hex_str), 2):
        b = int(hex_str[i : i + 2], 16)
        out.append(b)
    return out


def _le16(bytes_: list[int], index: int) -> int:
    return bytes_[index] | (bytes_[index + 1] << 8)


def _f10_to_c(raw_f10: int) -> float:
    f = raw_f10 / 10.0
    return (f - 32.0) / 1.8


def _extract_rssi(bytes_: list[int]) -> int:
    """Extract RSSI from position 1 using signed byte conversion."""
    return bytes_[1] - 256 if bytes_[1] >= 128 else bytes_[1]


def _extract_status_code(bytes_: list[int], hi_pos: int, lo_pos: int) -> int:
    """Extract status code from specified positions (little-endian)."""
    return (bytes_[hi_pos] << 8) | bytes_[lo_pos]


def _validate_payload(raw: str, min_length: int) -> list[int]:
    """Parse and validate basic payload structure."""
    b = _parse_homgar_payload(raw)
    if len(b) < min_length:
        raise ValueError(f"Payload too short: {b}")
    return b


def _validate_tag(bytes_: list[int], position: int, expected_tag: int, device_name: str) -> None:
    """Validate sensor tag at specific position."""
    if bytes_[position] != expected_tag:
        raise ValueError(f"{device_name}: Expected 0x{expected_tag:02x} tag at b[{position}], got 0x{bytes_[position]:02x}")


def _base_decoder_dict(device_type: str, rssi: int, raw_bytes: list[int]) -> dict:
    """Create base decoder return dictionary."""
    return {
        "type": device_type,
        "rssi_dbm": rssi,
        "raw_bytes": raw_bytes,
    }


def decode_moisture_simple(raw: str) -> dict:
    """
    Decode HCS026FRF (moisture-only) payload.
    Layout after '10#':
    b0 = 0xE1
    b1 = RSSI (signed int8)
    b2 = 0x00
    b3 = 0xDC
    b4 = 0x01
    b5 = 0x88  (moisture tag)
    b6 = moisture % (0-100)
    b7,b8 = status/battery field
    
    Based on actual payload: 10#E1C600DC01881AFF0F5E21F718
    E1 C6 00 DC 01 88 1A FF 0F 5E 21 F7 18
    b[1]=0xC6=198-256=-58 RSSI
    b[6]=0x1A=26% moisture
    """
    b = _validate_payload(raw, 9)
    _validate_tag(b, 5, 0x88, "HCS026FRF")
    
    rssi = _extract_rssi(b)
    moisture = b[6]
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("moisture_simple", rssi, b)
    result.update({
        "moisture_percent": moisture,
        "battery_status_code": status_code,
    })
    return result


def decode_moisture_full(raw: str) -> dict:
    """
    Decode HCS021FRF (moisture + temp + lux).
    Layout after '10#':
    b0 = 0xE1
    b1 = RSSI (signed)
    b2 = 0x00
    b3 = 0xDC
    b4 = 0x01
    b5 = 0x85
    b6,b7 = temp_raw F*10 LE
    b8     = 0x88  (moisture tag)
    b9     = moisture %
    b10    = 0xC6  (lux tag)
    b11,b12= lux_raw * 10 LE
    b13    = 0x00
    b14,b15= 0xFF,0x0F (status/battery)
    
    Based on actual payload: 10#E1A200DC0185AB02881FC6600600FF0FFA28F718
    E1 A2 00 DC 01 85 AB 02 88 1F C6 60 06 00 FF 0F FA 28 F7 18
    b[1]=0xA2=162-256=-94 RSSI
    b[6:7]=0x02AB=683°F*10 → 68.3°F → 20.2°C
    b[9]=0x1F=31% moisture
    b[11:12]=0x0660=1632 lux*10 → 163.2 lux
    """
    b = _validate_payload(raw, 16)
    _validate_tag(b, 5, 0x85, "HCS021FRF")
    
    rssi = _extract_rssi(b)
    temp_raw_f10 = _le16(b, 6)
    temp_c = _f10_to_c(temp_raw_f10)

    _validate_tag(b, 8, 0x88, "HCS021FRF")
    moisture = b[9]

    _validate_tag(b, 10, 0xC6, "HCS021FRF")
    lux_raw10 = _le16(b, 11)
    lux = lux_raw10 / 10.0

    status_code = _extract_status_code(b, 14, 15)

    result = _base_decoder_dict("moisture_full", rssi, b)
    result.update({
        "moisture_percent": moisture,
        "temperature_c": temp_c,
        "temperature_f10": temp_raw_f10,
        "illuminance_lux": lux,
        "illuminance_raw10": lux_raw10,
        "battery_status_code": status_code,
    })
    return result


def decode_rain(raw: str) -> dict:
    """
    Decode HCS012ARF (rain gauge).
    Layout after '10#':
    b0 = 0xE1
    b1 = 0x00 (seems constant in your samples)
    b2 = 0x00
    b3,4 = FD,04 ; b5,b6 = lastHour raw*10 LE
    b7,8 = FD,05 ; b9,b10 = last24h raw*10 LE
    b11,12 = FD,06 ; b13,b14 = last7d raw*10 LE
    b15,16 = DC,01
    b17 = 0x97 ; b18,b19 = total raw*10 LE
    b20,b21 = 0x00,0x00
    b22,b23 = 0xFF,0x0F (status/battery)
    b24..b27 = tail
    
    Based on actual payload: 10#E10000FD040000FD054E07FD064E07DC01974E070000FF0F0410F718
    E1 00 00 FD 04 00 00 FD 05 4E 07 FD 06 4E 07 DC 01 97 4E 07 00 00 FF 0F 04 10 F7 18
    b[5:6]=0x0000=0.0mm last hour
    b[9:10]=0x074E=1870mm*10 → 187.0mm last 24h
    b[13:14]=0x074E=1870mm*10 → 187.0mm last 7d
    b[18:19]=0x074E=1870mm*10 → 187.0mm total
    """
    b = _validate_payload(raw, 24)

    # Validate rain-specific tags
    if not (b[3] == 0xFD and b[4] == 0x04):
        raise ValueError("HCS012ARF: Missing FD 04 at [3:5]")
    if not (b[7] == 0xFD and b[8] == 0x05):
        raise ValueError("HCS012ARF: Missing FD 05 at [7:9]")
    if not (b[11] == 0xFD and b[12] == 0x06):
        raise ValueError("HCS012ARF: Missing FD 06 at [11:13]")
    _validate_tag(b, 17, 0x97, "HCS012ARF")

    last_hour_raw10 = _le16(b, 5)
    last_24h_raw10 = _le16(b, 9)
    last_7d_raw10 = _le16(b, 13)
    total_raw10 = _le16(b, 18)

    status_code = _extract_status_code(b, 22, 23)

    result = _base_decoder_dict("rain", 0, b)  # Rain gauge doesn't have RSSI in standard position
    result.update({
        "rain_last_hour_mm": last_hour_raw10 / 10.0,
        "rain_last_24h_mm": last_24h_raw10 / 10.0,
        "rain_last_7d_mm": last_7d_raw10 / 10.0,
        "rain_total_mm": total_raw10 / 10.0,
        "rain_last_hour_raw10": last_hour_raw10,
        "rain_last_24h_raw10": last_24h_raw10,
        "rain_last_7d_raw10": last_7d_raw10,
        "rain_total_raw10": total_raw10,
        "battery_status_code": status_code,
    })
    return result


# --- Additional decoders (stubs) for new sensor types ---
def decode_temphum(raw: str) -> dict:
    """
    Decode HCS014ARF (temperature/humidity) payload.
    """
    b = _validate_payload(raw, 40)  # Minimum length for basic data
    # See Node-RED: function "Temperature HCS014ARF"
    
    def le_val(parts):
        return int(''.join(f'{x:02x}' for x in parts[::-1]), 16)
    
    templow = (((le_val(b[7:9]+b[5:7]) / 10) - 32) * (5 / 9)) if len(b) >= 9 else None
    temphigh = (((le_val(b[11:13]+b[9:11]) / 10) - 32) * (5 / 9)) if len(b) >= 13 else None
    tempcurrent = (((le_val(b[25:27]+b[23:25]) / 10) - 32) * (5 / 9)) if len(b) >= 27 else None
    humiditycurrent = b[29] if len(b) > 29 else None
    humidityhigh = b[35] if len(b) > 35 else None
    humiditylow = b[33] if len(b) > 33 else None
    tempbatt = (le_val(b[39:41]+b[37:39]) / 4095 * 100) if len(b) >= 41 else None
    
    result = _base_decoder_dict("temphum", _extract_rssi(b), b)
    result.update({
        "templow": round(templow, 2) if templow is not None else None,
        "temphigh": round(temphigh, 2) if temphigh is not None else None,
        "tempcurrent": round(tempcurrent, 2) if tempcurrent is not None else None,
        "humiditycurrent": humiditycurrent,
        "humidityhigh": humidityhigh,
        "humiditylow": humiditylow,
        "tempbatt": round(tempbatt, 2) if tempbatt is not None else None,
    })
    return result

def decode_flowmeter(raw: str) -> dict:
    """
    Decode HCS008FRF (flowmeter) payload.
    """
    b = _validate_payload(raw, 111)  # Need full length for all data
    # See Node-RED: function "Flowmeter HCS008FRF"
    
    def le_val(parts):
        return int(''.join(f'{x:02x}' for x in parts[::-1]), 16)
    
    flowcurrentused = le_val(b[49:52]) / 10 if len(b) >= 52 else None
    flowcurrenduration = le_val(b[59:62]) if len(b) >= 62 else None
    flowlastused = le_val(b[69:72]) / 10 if len(b) >= 72 else None
    flowlastusedduration = le_val(b[81:84]) if len(b) >= 84 else None
    flowtotaltoday = le_val(b[91:94]) / 10 if len(b) >= 94 else None
    flowtotal = le_val(b[103:107]) / 10 if len(b) >= 107 else None
    flowbatt = le_val(b[107:111]) / 4095 * 100 if len(b) >= 111 else None
    
    result = _base_decoder_dict("flowmeter", _extract_rssi(b), b)
    result.update({
        "flowcurrentused": flowcurrentused,
        "flowcurrenduration": flowcurrenduration,
        "flowlastused": flowlastused,
        "flowlastusedduration": flowlastusedduration,
        "flowtotaltoday": flowtotaltoday,
        "flowtotal": flowtotal,
        "flowbatt": round(flowbatt, 2) if flowbatt is not None else None,
    })
    return result

def decode_co2(raw: str) -> dict:
    """
    Decode HCS0530THO (CO2/temp/humidity) payload.
    """
    b = _validate_payload(raw, 63)  # Minimum for basic CO2 data
    # See Node-RED: function "CO2 HCS0530THO"
    
    def le_val(parts):
        return int(''.join(f'{x:02x}' for x in parts[::-1]), 16)
    
    co2 = le_val(b[7:9]+b[5:7]) if len(b) >= 9 else None
    co2low = le_val(b[53:55]+b[51:53]) if len(b) >= 55 else None
    co2high = le_val(b[57:59]+b[55:57]) if len(b) >= 59 else None
    co2temp = (((le_val(b[35:37]+b[33:35]) / 10) - 32) * (5 / 9)) if len(b) >= 37 else None
    co2humidity = b[39] if len(b) > 39 else None
    co2batt = le_val(b[61:63]+b[59:61]) / 4095 * 100 if len(b) >= 63 else None
    co2rssi = b[67] - 256 if len(b) > 67 and b[67] > 127 else (b[67] if len(b) > 67 else None)
    
    result = _base_decoder_dict("co2", co2rssi if co2rssi is not None else _extract_rssi(b), b)
    result.update({
        "co2": co2,
        "co2low": co2low,
        "co2high": co2high,
        "co2temp": round(co2temp, 2) if co2temp is not None else None,
        "co2humidity": co2humidity,
        "co2batt": round(co2batt, 2) if co2batt is not None else None,
        "co2rssi": co2rssi,
    })
    return result

def decode_pool(raw: str) -> dict:
    """
    Decode HCS0528ARF (pool/temperature) payload.
    """
    b = _validate_payload(raw, 31)  # Minimum for basic data
    # See Node-RED: function "Pool"
    
    def le_val(parts):
        return int(''.join(f'{x:02x}' for x in parts[::-1]), 16)
    
    templow = (((le_val(b[7:9]+b[5:7]) / 10) - 32) * (5 / 9)) if len(b) >= 9 else None
    temphigh = (((le_val(b[11:13]+b[9:11]) / 10) - 32) * (5 / 9)) if len(b) >= 13 else None
    tempcurrent = (((le_val(b[25:27]+b[23:25]) / 10) - 32) * (5 / 9)) if len(b) >= 27 else None
    tempbatt = le_val(b[29:31]+b[25:27]) / 4095 * 100 if len(b) >= 31 else None
    
    result = _base_decoder_dict("pool", _extract_rssi(b), b)
    result.update({
        "templow": round(templow, 2) if templow is not None else None,
        "temphigh": round(temphigh, 2) if temphigh is not None else None,
        "tempcurrent": round(tempcurrent, 2) if tempcurrent is not None else None,
        "tempbatt": round(tempbatt, 2) if tempbatt is not None else None,
    })
    return result


def decode_pool_plus(raw: str) -> dict:
    """
    Decode HCS015ARF+ (pool + ambient temperature/humidity) payload.
    Layout (payload prefix 11#): pool temp 16-bit LE F*10 at b[2:4] (low/current),
    b[4:6] (high); ambient temp at b[29:31] (low), b[31:33] (current/high);
    humidity at b[25] (low), b[26] (current), b[15] (high).
    """
    b = _validate_payload(raw, 34)

    def le16(idx: int) -> int:
        return b[idx] | (b[idx + 1] << 8)

    def f10_to_c(val: int) -> float:
        return round((val / 10.0 - 32.0) * (5.0 / 9.0), 2)

    # Pool temperature: 16-bit LE F*10 at b[2:4] (current), b[4:6] (high).
    # Min is not present in payload (device may track it internally); avoid using
    # current for min so "Pool Low" doesn't incorrectly track the live reading.
    pool_raw_current = le16(2)
    pool_raw_high = le16(4)
    pool_tempcurrent = f10_to_c(pool_raw_current) if 400 <= pool_raw_current <= 1200 else None
    pool_temphigh = f10_to_c(pool_raw_high) if 400 <= pool_raw_high <= 1200 else None
    pool_templow = None  # not decoded from payload

    # Ambient temperature: 16-bit LE F*10 at b[29:31] (low/current), b[31:33] (high)
    ambient_templow = f10_to_c(le16(29)) if 400 <= le16(29) <= 1200 else None
    ambient_temphigh = f10_to_c(le16(31)) if 400 <= le16(31) <= 1200 else None
    ambient_tempcurrent = ambient_templow  # current from same slice as low

    # Ambient humidity: b[25]=low, b[26]=current, b[15]=high (0-100)
    humidity_low = b[25] if len(b) > 25 and 0 <= b[25] <= 100 else None
    humidity_current = b[26] if len(b) > 26 and 0 <= b[26] <= 100 else None
    humidity_high = b[15] if len(b) > 15 and 0 <= b[15] <= 100 else None

    result = _base_decoder_dict("pool_plus", _extract_rssi(b), b)
    result.update({
        "pool_templow": pool_templow,
        "pool_temphigh": pool_temphigh,
        "pool_tempcurrent": pool_tempcurrent,
        "ambient_templow": ambient_templow,
        "ambient_tempcurrent": ambient_tempcurrent,
        "ambient_temphigh": ambient_temphigh,
        "humidity_low": humidity_low,
        "humidity_current": humidity_current,
        "humidity_high": humidity_high,
    })
    return result


def _parse_tlv_payload(raw: str) -> dict[int, tuple[int, int, bytes]]:
    """
    Parse a TLV (Type-Length-Value) payload used by valve hubs.
    Returns dict: {dp_id: (type_byte, value_int, raw_bytes)}
    """
    b = _validate_payload(raw, 3)  # Minimum for one TLV entry
    tlv: dict[int, tuple[int, int, bytes]] = {}
    i = 0
    while i < len(b):
        if i + 2 >= len(b):
            break
        dp_id = b[i]
        type_byte = b[i + 1]
        length = b[i + 2]
        i += 3
        if i + length > len(b):
            break
        raw_bytes = bytes(b[i : i + length])
        value_int = int.from_bytes(raw_bytes, "big") if raw_bytes else 0
        tlv[dp_id] = (type_byte, value_int, raw_bytes)
        i += length
    return tlv


def decode_valve_hub(raw: str) -> dict:
    """
    Decode an irrigation valve hub TLV payload (e.g. HTV0540FRF).

    Confirmed DP map (derived from live payload capture):
      0x18      hub online state     DC  1-byte  0x01 = online
      0x18+N    zone N open state    D8  1-byte  0x00 = closed, non-zero = open
      0x24+N    zone N run duration  AD  2-byte  little-endian seconds

    Zone state DPs are detected dynamically from the payload so that hubs with
    any number of zones (1, 2, 3, 4, ...) are handled without code changes.
    """
    tlv = _parse_tlv_payload(raw)

    def get_val(dp: int) -> int | None:
        entry = tlv.get(dp)
        return entry[1] if entry else None

    def get_raw_bytes(dp: int) -> bytes:
        entry = tlv.get(dp)
        return entry[2] if entry else b""

    hub_state = get_val(_DP_HUB_STATE)

    # Dynamically detect zones: any DP of type 0xD8 (state byte) with
    # dp > _DP_HUB_STATE follows the pattern zone_num = dp - _DP_HUB_STATE.
    zones: dict[int, dict] = {}
    for dp, entry in tlv.items():
        type_byte = entry[0]
        if type_byte != 0xD8 or dp <= _DP_HUB_STATE:
            continue
        zone_num = dp - _DP_HUB_STATE
        state_val = entry[1]
        dur_dp = _DP_BASE_DURATION + zone_num
        dur_bytes = get_raw_bytes(dur_dp)
        duration_s = int.from_bytes(dur_bytes, "little") if len(dur_bytes) == 2 else None
        zones[zone_num] = {
            # Bit 0 = valve physically open. 0x21 = open, 0x20 = closing/transitional, 0x00 = closed.
            "open": bool(state_val & 0x01) if state_val is not None else None,
            "state_raw": state_val,
            "duration_seconds": duration_s,
        }

    result = _base_decoder_dict("valve_hub", 0, _parse_homgar_payload(raw))  # TLV doesn't use standard RSSI
    result.update({
        "hub_online": hub_state == 1,
        "hub_state_raw": hub_state,
        "zones": zones,
        "tlv_raw": tlv,
    })
    return result


# --- Additional Device Decoders ---

def decode_hcs005frf(raw: str) -> dict:
    """
    Decode HCS005FRF (moisture-only sensor).
    Layout: 10#E1[RSSI][00][DC][01][88][MOISTURE][STATUS_HI][STATUS_LO][TAIL...]
    """
    b = _validate_payload(raw, 9)
    _validate_tag(b, 5, 0x88, "HCS005FRF")
    
    rssi = _extract_rssi(b)
    moisture = b[6]
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs005frf", rssi, b)
    result.update({
        "device_model": "HCS005FRF",
        "moisture_percent": moisture,
        "battery_status_code": status_code,
    })
    return result


def decode_hcs003frf(raw: str) -> dict:
    """
    Decode HCS003FRF (moisture-only sensor).
    Layout: 10#E1[RSSI][00][DC][01][88][MOISTURE][STATUS_HI][STATUS_LO][TAIL...]
    """
    b = _validate_payload(raw, 9)
    _validate_tag(b, 5, 0x88, "HCS003FRF")
    
    rssi = _extract_rssi(b)
    moisture = b[6]
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs003frf", rssi, b)
    result.update({
        "device_model": "HCS003FRF",
        "moisture_percent": moisture,
        "battery_status_code": status_code,
    })
    return result


def decode_hcs024frf_v1(raw: str) -> dict:
    """
    Decode HCS024FRF-V1 (multi-sensor).
    Layout: 10#E1[RSSI][00][DC][01][85][TEMP_LO][TEMP_HI][88][MOISTURE][C6][LUX_LO][LUX_HI][00][STATUS_HI][STATUS_LO][TAIL...]
    """
    b = _validate_payload(raw, 16)
    _validate_tag(b, 5, 0x85, "HCS024FRF-V1")
    
    rssi = _extract_rssi(b)
    temp_raw_f10 = _le16(b, 6)
    temp_c = _f10_to_c(temp_raw_f10)

    _validate_tag(b, 8, 0x88, "HCS024FRF-V1")
    moisture = b[9]

    _validate_tag(b, 10, 0xC6, "HCS024FRF-V1")
    lux_raw10 = _le16(b, 11)
    lux = lux_raw10 / 10.0

    status_code = _extract_status_code(b, 14, 15)

    result = _base_decoder_dict("hcs024frf_v1", rssi, b)
    result.update({
        "device_model": "HCS024FRF-V1",
        "moisture_percent": moisture,
        "temperature_c": temp_c,
        "temperature_f10": temp_raw_f10,
        "illuminance_lux": lux,
        "illuminance_raw10": lux_raw10,
        "battery_status_code": status_code,
    })
    return result


def decode_hcs014arf(raw: str) -> dict:
    """
    Decode HCS014ARF (temperature/humidity sensor).
    Temperature/humidity sensor with complex multi-part data structures.
    """
    b = _validate_payload(raw, 40)
    
    # Temperature/humidity sensors use complex multi-part data structures
    def le_val(parts):
        return int(''.join(f'{x:02x}' for x in parts[::-1]), 16)
    
    rssi = _extract_rssi(b)
    
    templow = (((le_val(b[7:9]+b[5:7]) / 10) - 32) * (5 / 9)) if len(b) >= 9 else None
    temphigh = (((le_val(b[11:13]+b[9:11]) / 10) - 32) * (5 / 9)) if len(b) >= 13 else None
    tempcurrent = (((le_val(b[25:27]+b[23:25]) / 10) - 32) * (5 / 9)) if len(b) >= 27 else None
    humiditycurrent = b[29] if len(b) > 29 else None
    humidityhigh = b[35] if len(b) > 35 else None
    humiditylow = b[33] if len(b) > 33 else None
    tempbatt = (le_val(b[39:41]+b[37:39]) / 4095 * 100) if len(b) >= 41 else None

    result = _base_decoder_dict("hcs014arf", rssi, b)
    result.update({
        "device_model": "HCS014ARF",
        "templow": round(templow, 2) if templow is not None else None,
        "temphigh": round(temphigh, 2) if temphigh is not None else None,
        "tempcurrent": round(tempcurrent, 2) if tempcurrent is not None else None,
        "humiditycurrent": humiditycurrent,
        "humidityhigh": humidityhigh,
        "humiditylow": humiditylow,
        "tempbatt": round(tempbatt, 2) if tempbatt is not None else None,
    })
    return result


def decode_hcs015arf(raw: str) -> dict:
    """
    Decode HCS015ARF (pool temperature sensor).
    Pool temperature sensor with similar structure to other temperature sensors.
    """
    b = _validate_payload(raw, 31)
    
    def le_val(parts):
        return int(''.join(f'{x:02x}' for x in parts[::-1]), 16)
    
    rssi = _extract_rssi(b)
    
    # Pool temperature data - similar structure to other temp sensors
    templow = (((le_val(b[7:9]+b[5:7]) / 10) - 32) * (5 / 9)) if len(b) >= 9 else None
    temphigh = (((le_val(b[11:13]+b[9:11]) / 10) - 32) * (5 / 9)) if len(b) >= 13 else None
    tempcurrent = (((le_val(b[25:27]+b[23:25]) / 10) - 32) * (5 / 9)) if len(b) >= 27 else None
    tempbatt = le_val(b[29:31]+b[25:27]) / 4095 * 100 if len(b) >= 31 else None

    result = _base_decoder_dict("hcs015arf", rssi, b)
    result.update({
        "device_model": "HCS015ARF",
        "templow": round(templow, 2) if templow is not None else None,
        "temphigh": round(temphigh, 2) if temphigh is not None else None,
        "tempcurrent": round(tempcurrent, 2) if tempcurrent is not None else None,
        "tempbatt": round(tempbatt, 2) if tempbatt is not None else None,
    })
    return result


def decode_hcs0528arf(raw: str) -> dict:
    """
    Decode HCS0528ARF (pool temperature sensor).
    Pool temperature sensor - alias for decode_pool with proper device model.
    """
    result = decode_pool(raw)
    result["type"] = "hcs0528arf"
    result["device_model"] = "HCS0528ARF"
    return result


def decode_hcs027arf(raw: str) -> dict:
    """
    Decode HCS027ARF (unknown sensor type).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs027arf", rssi, b)
    result.update({
        "device_model": "HCS027ARF",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs016arf(raw: str) -> dict:
    """
    Decode HCS016ARF (unknown sensor type).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs016arf", rssi, b)
    result.update({
        "device_model": "HCS016ARF",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs044frf(raw: str) -> dict:
    """
    Decode HCS044FRF (unknown sensor type).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs044frf", rssi, b)
    result.update({
        "device_model": "HCS044FRF",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs666frf(raw: str) -> dict:
    """
    Decode HCS666FRF (unknown sensor variant).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs666frf", rssi, b)
    result.update({
        "device_model": "HCS666FRF",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs666rfr_p(raw: str) -> dict:
    """
    Decode HCS666RFR-P (unknown sensor variant).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs666rfr_p", rssi, b)
    result.update({
        "device_model": "HCS666RFR-P",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs999frf(raw: str) -> dict:
    """
    Decode HCS999FRF (unknown sensor variant).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs999frf", rssi, b)
    result.update({
        "device_model": "HCS999FRF",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs999frf_p(raw: str) -> dict:
    """
    Decode HCS999FRF-P (unknown sensor variant).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs999frf_p", rssi, b)
    result.update({
        "device_model": "HCS999FRF-P",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs666frf_x(raw: str) -> dict:
    """
    Decode HCS666FRF-X (unknown sensor variant).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs666frf_x", rssi, b)
    result.update({
        "device_model": "HCS666FRF-X",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs701b(raw: str) -> dict:
    """
    Decode HCS701B (unknown sensor type).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs701b", rssi, b)
    result.update({
        "device_model": "HCS701B",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs596wb(raw: str) -> dict:
    """
    Decode HCS596WB (unknown sensor type).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs596wb", rssi, b)
    result.update({
        "device_model": "HCS596WB",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs596wb_v4(raw: str) -> dict:
    """
    Decode HCS596WB-V4 (unknown sensor type).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs596wb_v4", rssi, b)
    result.update({
        "device_model": "HCS596WB-V4",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs706arf(raw: str) -> dict:
    """
    Decode HCS706ARF (unknown sensor type).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs706arf", rssi, b)
    result.update({
        "device_model": "HCS706ARF",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs802arf(raw: str) -> dict:
    """
    Decode HCS802ARF (unknown sensor type).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs802arf", rssi, b)
    result.update({
        "device_model": "HCS802ARF",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs048b(raw: str) -> dict:
    """
    Decode HCS048B (unknown sensor type).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs048b", rssi, b)
    result.update({
        "device_model": "HCS048B",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs888arf_v1(raw: str) -> dict:
    """
    Decode HCS888ARF-V1 (unknown sensor type).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs888arf_v1", rssi, b)
    result.update({
        "device_model": "HCS888ARF-V1",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result


def decode_hcs0600arf(raw: str) -> dict:
    """
    Decode HCS0600ARF (unknown sensor type).
    Basic sensor structure until real payload is available.
    """
    b = _validate_payload(raw, 9)
    rssi = _extract_rssi(b)
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("hcs0600arf", rssi, b)
    result.update({
        "device_model": "HCS0600ARF",
        "battery_status_code": status_code,
        "note": "Device type unknown - basic structure only",
    })
    return result
