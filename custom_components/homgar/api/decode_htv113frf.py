"""HTV113FRF 1-zone timer decoder.

Fixed-position payload format for HTV113FRF 1-zone timer devices.
Based on analysis of real device payload from Shaun's setup.

Device: HTV113FRF (1-zone timer)
Payload: 10#E1D500DC01D80020B700000000AD00009F00000000FF0FB1440D19
"""

from typing import Dict, Any


def decode_htv113frf(payload: str) -> Dict[str, Any]:
    """Decode HTV113FRF 1-zone timer payload.
    
    Args:
        payload: Raw payload string (e.g., "10#E1D500DC01D80020B700000000AD00009F00000000FF0FB1440D19")
        
    Returns:
        Dictionary containing decoded timer data
    """
    # Extract hex part after "10#" prefix
    if payload.startswith("10#"):
        hex_part = payload[3:]
    else:
        hex_part = payload
    
    # Convert to bytes
    try:
        bytes_list = [int(hex_part[i:i+2], 16) for i in range(0, len(hex_part), 2)]
    except ValueError:
        return {"type": "unknown", "model": "HTV113FRF", "error": "Invalid hex payload"}
    
    # Need at least 27 bytes for complete data
    if len(bytes_list) < 27:
        return {"type": "unknown", "model": "HTV113FRF", "error": f"Insufficient data: {len(bytes_list)} bytes"}
    
    # Extract data based on fixed position analysis
    decoded = {
        "type": "timer",
        "model": "HTV113FRF",
        "zones": {},  # 1-zone timer
    }
    
    # RSSI (position 0) - signed byte
    rssi_raw = bytes_list[0]
    rssi = rssi_raw - 256 if rssi_raw > 127 else rssi_raw
    decoded["rssi_dbm"] = rssi
    
    # Battery status (positions 21-22) - FF0F = 100%
    battery_high = bytes_list[21]
    battery_low = bytes_list[22]
    if battery_high == 0xFF and battery_low == 0x0F:
        decoded["battery_percent"] = 100
    elif battery_low <= 100:
        decoded["battery_percent"] = battery_low
    else:
        decoded["battery_percent"] = None
    
    # Zone 1 state (position 8) - bit analysis
    zone_state_byte = bytes_list[8]
    zone_open = bool(zone_state_byte & 0x01)  # LSB indicates open/closed
    decoded["zones"][1] = {
        "open": zone_open,
        "duration_seconds": 0,  # Default duration
    }
    
    # Duration (position 13) - if non-zero, use as duration
    duration_raw = bytes_list[13]
    if duration_raw > 0 and duration_raw <= 255:
        decoded["zones"][1]["duration_seconds"] = duration_raw
    
    # Additional timer-specific data
    decoded.update({
        "timer_mode": None,  # Could be derived from other bytes
        "countdown_active": False,  # Could be derived from other bytes
        "raw_bytes": bytes_list,  # For debugging
    })
    
    # Try to extract timer mode from other positions
    # Position 4 might indicate mode
    mode_byte = bytes_list[4]
    if mode_byte == 1:
        decoded["timer_mode"] = "auto"
    elif mode_byte == 2:
        decoded["timer_mode"] = "manual"
    
    # Position 7 might indicate countdown status
    status_byte = bytes_list[7]
    if status_byte & 0x20:  # Check bit 5
        decoded["countdown_active"] = True
    
    return decoded


# Test function for development
def _test_decode():
    """Test the decoder with known payload."""
    test_payload = "10#E1D500DC01D80020B700000000AD00009F00000000FF0FB1440D19"
    result = decode_htv113frf(test_payload)
    print("HTV113FRF Decoder Test:")
    print(f"Input: {test_payload}")
    print(f"Output: {result}")
    return result


if __name__ == "__main__":
    _test_decode()
