"""Decoder for HTV113FRF 1-zone timer."""
import logging
from ..utils import _parse_homgar_payload

_LOGGER = logging.getLogger(__name__)


def decode_htv113frf(raw: str) -> dict:
    """Decode HTV113FRF 1-zone timer payload."""
    from ...const import debug_with_version

    result = {
        "type": "timer",
        "model": "HTV113FRF",
        "zones": {},
    }

    try:
        bytes_list = _parse_homgar_payload(raw)
        if not bytes_list or len(bytes_list) < 27:
            result.update({"type": "unknown", "error": f"Insufficient data: {len(bytes_list) if bytes_list else 0} bytes"})
            return result

        rssi_raw = bytes_list[0]
        result["rssi_dbm"] = rssi_raw - 256 if rssi_raw > 127 else rssi_raw

        battery_high = bytes_list[21]
        battery_low = bytes_list[22]
        if battery_high == 0xFF and battery_low == 0x0F:
            result["battery_percent"] = 100
        elif battery_low <= 100:
            result["battery_percent"] = battery_low
        else:
            result["battery_percent"] = None

        zone_state_byte = bytes_list[8]
        result["zones"][1] = {
            "open": bool(zone_state_byte & 0x01),
            "duration_seconds": 0,
        }

        duration_raw = bytes_list[13]
        if 0 < duration_raw <= 255:
            result["zones"][1]["duration_seconds"] = duration_raw

        result.update({
            "timer_mode": None,
            "countdown_active": False,
            "raw_bytes": bytes_list,
            "hub_online": True,
        })

        mode_byte = bytes_list[4]
        if mode_byte == 1:
            result["timer_mode"] = "auto"
        elif mode_byte == 2:
            result["timer_mode"] = "manual"

        if bytes_list[7] & 0x20:
            result["countdown_active"] = True

        _LOGGER.debug(debug_with_version("HTV113FRF decoded: zones=%s, rssi=%d, battery=%s%%"),
                      result["zones"], result["rssi_dbm"], result["battery_percent"])

    except Exception as e:
        _LOGGER.error(debug_with_version("Error in HTV113FRF decoder: %s"), e)
        result.update({"type": "unknown", "error": str(e)})

    return result
