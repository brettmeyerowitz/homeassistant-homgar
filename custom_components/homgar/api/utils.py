"""
Utility functions for HomGar API.

This module contains helper functions for payload parsing, data conversion,
and common operations used across the API.
"""

import logging
import re

_LOGGER = logging.getLogger(__name__)

_STATS_RE = re.compile(r'^(\d+)\((\d+)/(\d+)/(\d+)\)')


def _parse_stats(s: str):
    """Parse 'value(max/min/trend)' format. Returns (current, max, min) or (value, None, None)."""
    m = _STATS_RE.match(s.strip())
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return int(s.strip()), None, None
    except (ValueError, TypeError):
        return None, None, None


def _parse_ascii_sensor_payload(raw: str):
    """Parse EU-format ASCII sensor payload: 'battery,rssi,extra;field1,field2,...'

    Returns (fields, battery_code, rssi_dbm) where fields is a list of stripped strings.
    Returns None if the payload does not match this format (no semicolon, or has '#').
    """
    if '#' in raw or ';' not in raw:
        return None, None, None
    parts = raw.split(';', 1)
    prefix_parts = [x.strip() for x in parts[0].split(',') if x.strip()]
    battery_code = int(prefix_parts[0]) if prefix_parts else None
    rssi_dbm = -int(prefix_parts[1]) if len(prefix_parts) >= 2 else None
    fields = [f.strip() for f in parts[1].split(',') if f.strip()]
    return fields, battery_code, rssi_dbm


def _parse_homgar_payload(raw: str) -> bytes:
    """Parse a HomGar hex payload and return bytes."""
    if "#" not in raw:
        raise ValueError("Payload missing '#' separator")
    
    prefix, hex_data = raw.split("#", 1)
    
    # Handle different formats
    if prefix in ("10", "00"):
        # Standard format: 10#ABCDEF... (00# is an alternate form of same format)
        return bytes.fromhex(hex_data)
    elif prefix == "11":
        # TLV format: 11#ABCDEF...
        return bytes.fromhex(hex_data)
    else:
        raise ValueError(f"Unknown payload prefix: {prefix}")


def _parse_tlv_payload(raw: str) -> dict:
    """
    Parse TLV (Type-Length-Value) payload for valve hub (11# prefix).
    
    Format: DP_ID (1 byte) + TYPE (1 byte) + VALUE (variable length based on type)
    
    Type byte determines value width:
    - 0xD8: 1 byte
    - 0xDC: 1 byte  
    - 0xB7: 4 bytes
    - 0xAD: 2 bytes
    - 0xE1: 2 bytes
    - 0xC4, 0xC5, 0xC6: 1 byte
    - 0x20: 0 bytes (flag)
    
    Returns a dictionary mapping DP IDs to (type_byte, value_int, raw_bytes).
    """
    # Type byte -> value width in bytes
    _TLV_TYPE_WIDTHS = {
        0xD8: 1,
        0xDC: 1,
        0xB7: 4,
        0xAD: 2,
        0xE1: 2,
        0xC4: 1,
        0xC5: 1,
        0xC6: 1,
        0x20: 0,
        0xFF: 1,
    }
    
    b = _parse_homgar_payload(raw)
    tlv = {}
    i = 0
    
    while i < len(b):
        if i + 1 >= len(b):
            break
            
        dp_id = b[i]
        type_byte = b[i + 1]
        
        # Unknown type - try to resync
        if type_byte not in _TLV_TYPE_WIDTHS:
            i += 1
            continue
            
        width = _TLV_TYPE_WIDTHS[type_byte]
        
        if i + 2 + width > len(b):
            break
            
        raw_bytes = bytes(b[i + 2 : i + 2 + width])
        # Use big-endian for most values; caller handles little-endian for specific DPs
        value_int = int.from_bytes(raw_bytes, "big") if width > 0 else None
        tlv[dp_id] = (type_byte, value_int, raw_bytes)
        i += 2 + width
        
    return tlv


def _le16(b: bytes, offset: int) -> int:
    """Extract little-endian 16-bit integer from bytes at offset."""
    return int.from_bytes(b[offset : offset + 2], "little")


def _f10_to_c(temp_raw_f10: int) -> float:
    """Convert temperature from F*10 to Celsius."""
    return (temp_raw_f10 / 10.0 - 32.0) * 5.0 / 9.0


def _base_decoder_dict(device_type: str, rssi: int, raw_bytes: bytes) -> dict:
    """Create base decoder dictionary with common fields."""
    return {
        "type": device_type,
        "rssi_dbm": rssi,
        "raw_bytes": raw_bytes,
    }
