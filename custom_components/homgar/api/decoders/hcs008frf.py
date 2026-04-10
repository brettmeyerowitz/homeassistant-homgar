"""Decoder for HCS008FRF Flow Meter."""
import logging
from ..utils import _parse_homgar_payload, _parse_ascii_sensor_payload, _parse_stats
from ..validators import _extract_rssi

_LOGGER = logging.getLogger(__name__)


def decode_hcs008frf(raw: str) -> dict:
    """Decode HCS008FRF (flow meter) using fixed byte positions.

    Based on Excel formulas from Shaun (issue #27), with correction for Total field (v2.1.6):
    - Current Water Usage: bytes 22-24 (3 bytes, little-endian)
    - Current Duration: bytes 27-29 (3 bytes, little-endian)
    - Last Water Usage: bytes 32-34 (3 bytes, little-endian)
    - Last Duration: bytes 38-40 (3 bytes, little-endian)
    - Total Today: bytes 43-45 (3 bytes, little-endian)
    - Total: bytes 47-50 (4 bytes, little-endian) / 10 - before FF 0F DP marker
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
        
        # Try ASCII format first: "1,-71,1;31A01419,28,5485,..."
        fields, battery_code, rssi_dbm = _parse_ascii_sensor_payload(raw)
        if fields is not None:
            # ASCII format: fields after semicolon
            # fields[0] might be hex status, fields[1+] are values
            _LOGGER.debug(debug_with_version("HCS008FRF ASCII format: %d fields"), len(fields))
            # For now, return basic info - TODO: parse ASCII flow values
            # Battery not in ASCII payload, assume 100%
            return {
                "type": "flowmeter",
                "device_model": "HCS008FRF",
                "rssi_dbm": rssi_dbm or 0,
                "flowbatt": 100,
                "decoder": "hcs008frf_ascii_placeholder",
            }
        
        # Fall back to hex format: 10#...
        b = _parse_homgar_payload(raw)
        if not b or len(b) < 54:
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
        # Total: 4 bytes at 47-50 (before FF 0F DP marker) / 10 (not 1000)
        # Verified with Shaun's payload: 98586 -> 9858.6 L
        result["flowtotal"] = int.from_bytes(b[47:51], 'little') / 10.0
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

