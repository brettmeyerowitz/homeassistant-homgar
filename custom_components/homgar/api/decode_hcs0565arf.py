"""
Decoder for HCS0565ARF Pool Temperature Sensor.

This is a newer pool temperature sensor model with a similar structure to HCS0528ARF.
Payload format: 10#E7DE020503DC01B805850503FF0F61EB0C19

Temperature is stored at position 3 as F*10 (little-endian 16-bit).
"""

import logging
from .utils import _parse_homgar_payload, _le16, _f10_to_c
from .validators import _extract_rssi, _battery_status_to_percent

_LOGGER = logging.getLogger(__name__)


def decode_hcs0565arf(raw: str) -> dict:
    """
    Decode HCS0565ARF pool temperature sensor.
    
    Payload structure (18 bytes):
    - Byte 0: RSSI
    - Bytes 1-2: Unknown (possibly low temp)
    - Bytes 3-4: Current temperature (F*10, little-endian)
    - Bytes 5-11: Unknown/status
    - Bytes 12-13: Battery indicator (0xFF0F = 100%)
    - Bytes 14-17: Timestamp/tail
    
    Example: 10#E7DE020503DC01B805850503FF0F61EB0C19
    - Position 3-4: 0x0305 = 773 (77.3°F = 25.2°C)
    """
    from ..const import debug_with_version
    
    _LOGGER.debug(debug_with_version("Decoding HCS0565ARF: %s"), raw)
    
    result = {
        "type": "pool",
        "device_model": "HCS0565ARF",
        "temperature_current_f": None,
        "temperature_current_c": None,
        "temperature_low_f": None,
        "temperature_high_f": None,
        "rssi_dbm": None,
        "battery_percent": None,
        "decoder": "hcs0565arf",
    }
    
    try:
        b = _parse_homgar_payload(raw)
        
        if len(b) < 18:
            _LOGGER.warning(debug_with_version("HCS0565ARF payload too short: %d bytes"), len(b))
            return result
        
        # Extract RSSI from first byte
        result["rssi_dbm"] = _extract_rssi(b)
        
        # Extract current temperature from position 3-4 (F*10, little-endian)
        temp_f10 = _le16(b, 3)
        result["temperature_current_f"] = temp_f10 / 10.0
        result["temperature_current_c"] = _f10_to_c(temp_f10)
        
        _LOGGER.debug(debug_with_version("HCS0565ARF temp: %.1f°F (%.1f°C)"),
                     result["temperature_current_f"], result["temperature_current_c"])
        
        # Check for battery indicator at position 12-13
        if b[12] == 0xFF and b[13] == 0x0F:
            result["battery_percent"] = 100
        else:
            # Try to extract battery status if different format
            battery_status = (b[12] << 8) | b[13]
            result["battery_percent"] = _battery_status_to_percent(battery_status)
        
        # Low and high temps appear to be at other positions or not present
        # Set to 0.0 for now (similar to HCS0528ARF behavior)
        result["temperature_low_f"] = 0.0
        result["temperature_high_f"] = 0.0
        
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in HCS0565ARF decoder: %s"), e)
        result["decoder"] = "error"
        result["error"] = str(e)
    
    return result
