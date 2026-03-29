"""
Utility functions for HomGar API.

This module contains helper functions for payload parsing, data conversion,
and common operations used across the API.
"""

import logging

_LOGGER = logging.getLogger(__name__)


def _parse_homgar_payload(raw: str) -> bytes:
    """Parse a HomGar hex payload and return bytes."""
    if "#" not in raw:
        raise ValueError("Payload missing '#' separator")
    
    prefix, hex_data = raw.split("#", 1)
    
    # Handle different formats
    if prefix == "10":
        # Standard format: 10#ABCDEF...
        return bytes.fromhex(hex_data)
    elif prefix == "11":
        # TLV format: 11#ABCDEF...
        return bytes.fromhex(hex_data)
    else:
        raise ValueError(f"Unknown payload prefix: {prefix}")


def _parse_tlv_payload(raw: str) -> dict:
    """
    Parse TLV (Type-Length-Value) payload.
    
    Returns a dictionary mapping DP IDs to (type_byte, value_int, raw_bytes).
    """
    b = _parse_homgar_payload(raw)
    tlv = {}
    i = 0
    
    while i < len(b):
        if i + 2 >= len(b):
            break
            
        dp_id = b[i]
        type_byte = b[i + 1]
        
        if i + 2 >= len(b):
            break
            
        length = b[i + 2]
        i += 3
        
        if i + length > len(b):
            break
            
        raw_bytes = bytes(b[i : i + length])
        value_int = int.from_bytes(raw_bytes, "big") if raw_bytes else 0
        tlv[dp_id] = (type_byte, value_int, raw_bytes)
        i += length
        
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
