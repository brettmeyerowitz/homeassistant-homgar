"""Decoder for HCS008FRF Flow Meter."""
import logging
from ..utils import _parse_homgar_payload
from ..validators import _extract_rssi

_LOGGER = logging.getLogger(__name__)


def decode_hcs008frf(raw: str) -> dict:
    """Decode HCS008FRF (flow meter) using fixed byte positions.
    
    Based on Excel formulas from Shaun (issue #27), with correction for Total field:
    - Current Water Usage: bytes 22-24 (3 bytes, little-endian)
    - Current Duration: bytes 27-29 (3 bytes, little-endian)
    - Last Water Usage: bytes 32-34 (3 bytes, little-endian)
    - Last Duration: bytes 38-40 (3 bytes, little-endian)
    - Total Today: bytes 43-45 (3 bytes, little-endian)
    - Total: bytes 51-53 (3 bytes, little-endian) - corrected from 48-51 to avoid 0xFF DP marker
    """
    from ...const import debug_with_version

    _LOGGER.debug(debug_with_version("Decoding HCS008FRF: %s"), raw)

    result = {
        "type": "flowmeter",
        "device_model": "HCS008FRF",
        "flowcurrentused": None,
        "flowcurrenduration": None,
        "flowlastused": None,
        "flowlastusedduration": None,
        "flowtotaltoday": None,
        "flowtotal": None,
        "flowbatt": None,
        "rssi_dbm": None,
        "decoder": "fixed_position",
    }

    try:
        # Ensure raw is a string (handle bytes or other types)
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8', errors='replace')
        raw = str(raw)
        
        _LOGGER.debug(debug_with_version("HCS008FRF normalized payload: %r"), raw)
        
        b = _parse_homgar_payload(raw)
        if not b or len(b) < 52:
            _LOGGER.warning(debug_with_version("HCS008FRF payload too short: %d bytes"), len(b) if b else 0)
            return result

        result["rssi_dbm"] = _extract_rssi(b)

        # Fixed byte positions from Shaun's Excel formulas (issue #27)
        # All values are little-endian, in milliliters (divide by 1000 for liters)
        result["flowcurrentused"] = int.from_bytes(b[22:25], 'little') / 1000.0
        result["flowcurrenduration"] = int.from_bytes(b[27:30], 'little')  # seconds
        result["flowlastused"] = int.from_bytes(b[32:35], 'little') / 1000.0
        result["flowlastusedduration"] = int.from_bytes(b[38:41], 'little')  # seconds
        result["flowtotaltoday"] = int.from_bytes(b[43:46], 'little') / 1000.0
        # Total: 3 bytes at 51-53 (byte 48-51 includes 0xFF DP marker, corrupting 4-byte read)
        result["flowtotal"] = int.from_bytes(b[51:54], 'little') / 1000.0
        result["flowbatt"] = 100  # Battery level not in payload, assume 100%

        _LOGGER.info(
            debug_with_version("HCS008FRF decoded: current=%.3fL, today=%.3fL, total=%.3fL"),
            result["flowcurrentused"],
            result["flowtotaltoday"],
            result["flowtotal"]
        )

    except Exception as e:
        _LOGGER.error(
            debug_with_version("Error in HCS008FRF decoder: %s (raw=%r, type=%s)"),
            e, raw, type(raw).__name__
        )
        result["decoder"] = "error"
        result["error"] = str(e)

    return result

