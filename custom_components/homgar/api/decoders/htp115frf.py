"""Decoder for HTP115FRF pump device.

Based on reverse-engineered Java logic from DevicePanel.java.
Uses TLV (Type-Length-Value) parsing with the following type codes:
- 0x01 (1): Work mode (WK_STATE) - pump state
- 0x05 (5): Duration (DURATION) - current session seconds
- 0x0F (15): Last water usage (LAST_USAGE) - tenths of liters
- 0x15 (21): Battery (BAT) - single byte percentage
- 0x21 (33): RSSI - single byte signed dBm
"""
import logging
import struct
from ..utils import _parse_homgar_payload

_LOGGER = logging.getLogger(__name__)

# Type codes from DpStatusCode enum
_TYPE_WORK_MODE = 0x01      # WK_STATE
_TYPE_ALARM = 0x02          # ALARM
_TYPE_DURATION = 0x05       # DURATION
_TYPE_LAST_USAGE = 0x0F     # LAST_USAGE (tenths of L)
_TYPE_BATTERY = 0x15        # BAT
_TYPE_RSSI = 0x21           # RSSI
_TYPE_EVENT_TIME = 0x29     # EVENT_TIME

# Work mode labels
WORK_MODES = {
    0: "idle",
    1: "irrigation",
    2: "mist",
    3: "cycle",
    4: "soak",
}


def _parse_tlv_payload(bytes_list: list) -> dict:
    """Parse TLV (Type-Length-Value) format from raw bytes.
    
    Format: [type_code, type_len, value0, value1, ...] for each entry
    Entries are sequential in the byte array.
    """
    entries = {}
    i = 0
    while i < len(bytes_list):
        if i + 1 >= len(bytes_list):
            break
        type_code = bytes_list[i]
        type_len = bytes_list[i + 1]
        
        # Calculate value bytes (type_len bytes after the header)
        value_end = i + 2 + type_len
        if value_end > len(bytes_list):
            _LOGGER.debug("TLV parse: truncated entry at position %d", i)
            break
            
        type_value = bytes_list[i + 2:value_end]
        entries[type_code] = {
            "type_code": type_code,
            "type_len": type_len,
            "type_value": type_value,
            "position": i,
        }
        i = value_end
    
    return entries


def _find_entry(entries: dict, type_code: int) -> dict | None:
    """Find TLV entry by type code."""
    return entries.get(type_code)


def _le_int(entry: dict) -> int:
    """Convert little-endian type_value bytes to int."""
    if not entry or entry["type_len"] <= 0:
        return 0
    payload = entry["type_value"]
    if len(payload) == 1:
        return payload[0] & 0xFF
    elif len(payload) == 2:
        return payload[0] | (payload[1] << 8)
    elif len(payload) == 3:
        return payload[0] | (payload[1] << 8) | (payload[2] << 16)
    elif len(payload) >= 4:
        return struct.unpack_from("<I", bytes(payload + [0] * 4))[0]
    return 0


def decode_htp115frf(raw: str) -> dict:
    """Decode HTP115FRF pump device payload using TLV parsing.
    
    Returns dict with:
    - work_mode: "idle", "irrigation", "mist", "cycle", "soak"
    - duration_sec: current session duration in seconds
    - last_usage_ml: last water consumption in milliliters
    - battery_percent: battery level (0-100)
    - rssi_dbm: signal strength in dBm (negative)
    - alarm: boolean alarm state
    """
    from ...const import debug_with_version
    
    _LOGGER.debug(debug_with_version("Decoding HTP115FRF: %s"), raw)
    
    result = {
        "type": "pump",
        "device_model": "HTP115FRF",
        "work_mode": None,
        "duration_sec": 0,
        "last_usage_ml": 0,
        "battery_percent": None,
        "rssi_dbm": None,
        "alarm": False,
        "decoder": "htp115frf_tlv",
    }
    
    try:
        # Ensure raw is string
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8', errors='replace')
        raw = str(raw)
        
        # Parse hex payload
        bytes_list = _parse_homgar_payload(raw)
        if not bytes_list or len(bytes_list) < 10:
            _LOGGER.warning(debug_with_version("HTP115FRF payload too short: %d bytes"), 
                          len(bytes_list) if bytes_list else 0)
            return result
        
        # Parse TLV entries
        entries = _parse_tlv_payload(bytes_list)
        _LOGGER.debug(debug_with_version("HTP115FRF parsed %d TLV entries"), len(entries))
        
        # Work mode (type 0x01)
        work_mode_entry = _find_entry(entries, _TYPE_WORK_MODE)
        if work_mode_entry:
            mode_raw = work_mode_entry["type_value"][0] & 0x0F if work_mode_entry["type_value"] else 0
            result["work_mode"] = WORK_MODES.get(mode_raw, f"unknown_{mode_raw}")
            result["is_running"] = mode_raw > 0
        
        # Duration (type 0x05)
        duration_entry = _find_entry(entries, _TYPE_DURATION)
        if duration_entry:
            result["duration_sec"] = _le_int(duration_entry)
        
        # Last water usage (type 0x0F) - in tenths of liters
        last_usage_entry = _find_entry(entries, _TYPE_LAST_USAGE)
        if last_usage_entry:
            raw_usage = _le_int(last_usage_entry)
            result["last_usage_ml"] = raw_usage * 100  # Convert tenths of L to mL
            result["last_usage_l"] = raw_usage / 10.0  # Also provide as liters
        
        # Battery (type 0x15)
        battery_entry = _find_entry(entries, _TYPE_BATTERY)
        if battery_entry and battery_entry["type_value"]:
            bat_raw = battery_entry["type_value"][0] & 0xFF
            # 0xFF or 255 usually means unknown/full
            if bat_raw == 255:
                result["battery_percent"] = 100
            else:
                result["battery_percent"] = bat_raw
        
        # RSSI (type 0x21) - signed byte
        rssi_entry = _find_entry(entries, _TYPE_RSSI)
        if rssi_entry and rssi_entry["type_value"]:
            rssi_raw = rssi_entry["type_value"][0]
            result["rssi_dbm"] = rssi_raw - 256 if rssi_raw > 127 else rssi_raw
        
        # Alarm (type 0x02)
        alarm_entry = _find_entry(entries, _TYPE_ALARM)
        if alarm_entry and alarm_entry["type_value"]:
            alarm_raw = alarm_entry["type_value"][0] & 0x0F
            result["alarm"] = alarm_raw > 0
        
        _LOGGER.info(
            debug_with_version("HTP115FRF decoded: mode=%s, duration=%ds, last=%.1fL, batt=%s%%, rssi=%sdBm"),
            result["work_mode"],
            result["duration_sec"],
            result.get("last_usage_l", 0),
            result["battery_percent"],
            result["rssi_dbm"]
        )
        
    except Exception as e:
        _LOGGER.error(
            debug_with_version("Error in HTP115FRF decoder: %s (raw=%r)"),
            e, raw, exc_info=True
        )
        result["decoder"] = "htp115frf_error"
        result["error"] = str(e)
    
    return result
