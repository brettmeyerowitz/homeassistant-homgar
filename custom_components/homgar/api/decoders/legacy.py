"""Legacy / stub decoders for device types not yet fully reverse-engineered."""
import logging
from ..utils import _parse_homgar_payload
from ..validators import _extract_rssi

_LOGGER = logging.getLogger(__name__)


def decode_unknown(raw: str) -> dict:
    """Decode unknown device — returns raw bytes for diagnostics."""
    from ...const import debug_with_version
    _LOGGER.debug(debug_with_version("Decoding unknown device: %s"), raw)
    result = {"type": "unknown", "rssi": None, "decoder": "basic"}
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in unknown decoder: %s"), e)
    return result


def decode_soil(raw: str) -> dict:
    """Decode soil sensor (stub)."""
    from ...const import debug_with_version
    _LOGGER.debug(debug_with_version("Decoding soil sensor: %s"), raw)
    result = {"type": "soil", "rssi": None, "decoder": "basic"}
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in soil decoder: %s"), e)
    return result


def decode_temp_hum(raw: str) -> dict:
    """Decode temperature/humidity sensor (stub)."""
    from ...const import debug_with_version
    _LOGGER.debug(debug_with_version("Decoding temp/hum sensor: %s"), raw)
    result = {"type": "temphum", "rssi": None, "decoder": "basic"}
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in temp/hum decoder: %s"), e)
    return result


def decode_temp_hum_full(raw: str) -> dict:
    """Decode full temperature/humidity sensor (stub)."""
    from ...const import debug_with_version
    _LOGGER.debug(debug_with_version("Decoding full temp/hum sensor: %s"), raw)
    result = {"type": "temphum_full", "rssi": None, "decoder": "basic"}
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in full temp/hum decoder: %s"), e)
    return result


def decode_display(raw: str) -> dict:
    """Decode display sensor (stub)."""
    from ...const import debug_with_version
    _LOGGER.debug(debug_with_version("Decoding display sensor: %s"), raw)
    result = {"type": "display", "rssi": None, "decoder": "basic"}
    try:
        b = _parse_homgar_payload(raw)
        if b and len(b) > 1:
            result["rssi"] = _extract_rssi(b)
            result["raw_bytes"] = b
    except Exception as e:
        _LOGGER.error(debug_with_version("Error in display decoder: %s"), e)
    return result
