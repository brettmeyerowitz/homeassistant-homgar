"""Decoder for HIC801W 8-zone WiFi irrigation controller."""
import logging
from ..utils import _parse_homgar_payload
from ..validators import _extract_rssi

_LOGGER = logging.getLogger(__name__)

_NUM_ZONES = 8


def decode_hic801w(raw: str) -> dict:
    """Decode HIC801W 8-zone WiFi irrigation controller payload.

    Payload format (10# prefix):
      [0]  RSSI high byte
      [1]  RSSI low byte (signed)
      [2]  unknown
      [3]  zone state bitmask (bit N = zone N+1 open)
      [4-7] unknown
      [8]  type marker 0xB7
      [9-12] flow/counter (LE 32-bit)
      [13] type marker 0xD8
      [14] hub state
      ...
      [20] 0xF9
      [21] battery high (0xFF = full)
      [22] battery low (0x00)
    """
    from ...const import debug_with_version
    result = {
        "type": "wifi_controller",
        "zones": {},
        "rssi_dbm": 0,
        "battery_percent": None,
        "hub_online": True,
        "decoder": "hic801w",
    }
    try:
        b = _parse_homgar_payload(raw)
        result["rssi_dbm"] = _extract_rssi(b) if len(b) > 1 else 0

        zone_bitmask = b[3] if len(b) > 3 else 0
        for zone_num in range(1, _NUM_ZONES + 1):
            open_state = bool(zone_bitmask & (1 << (zone_num - 1)))
            result["zones"][zone_num] = {
                "open": open_state,
                "state_raw": zone_bitmask,
                "duration_seconds": 0,
            }

        if len(b) > 22 and b[21] == 0xFF and b[22] == 0x00:
            result["battery_percent"] = 100
        elif len(b) > 22 and b[22] <= 100:
            result["battery_percent"] = b[22]

        _LOGGER.debug(debug_with_version("HIC801W decoded: %d zones, rssi=%d, bitmask=0x%02X"),
                      _NUM_ZONES, result["rssi_dbm"], zone_bitmask)
    except Exception as e:
        _LOGGER.error(debug_with_version("HIC801W decoder error: %s"), e)

    return result
