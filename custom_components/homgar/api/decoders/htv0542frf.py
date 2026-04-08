"""Decoder for HTV0542FRF 4-zone valve controller."""
import logging
from ..utils import _parse_homgar_payload, _base_decoder_dict
from ..validators import _extract_rssi

_LOGGER = logging.getLogger(__name__)


def decode_htv0542frf(raw: str) -> dict:
    """Decode HTV0542FRF 4-zone valve controller payload."""
    from ...const import debug_with_version

    _LOGGER.debug(debug_with_version("Decoding HTV0542FRF: %s"), raw)

    try:
        b = _parse_homgar_payload(raw)

        if not b or len(b) < 20:
            raise ValueError(f"HTV0542FRF payload too short: {len(b) if b else 0} bytes")

        rssi_dbm = -b[1] if b[1] > 0 else 0

        zones = {}
        i = 4
        while i + 2 < len(b):
            zone_id = b[i]
            if 0x19 <= zone_id <= 0x1C:
                zone_num = zone_id - 0x18
                state = b[i + 1]
                duration_byte = b[i + 2] if i + 2 < len(b) else 0
                is_open = bool(state & 0x01)
                zones[zone_num] = {
                    "open": is_open,
                    "state_raw": state,
                    "duration_raw": duration_byte,
                    "zone_id": zone_id,
                }
                i += 3
            else:
                i += 1
            if len(zones) >= 4:
                break

        hub_online = False
        for i in range(len(b) - 1):
            if b[i] == 0x18:
                hub_state_byte = b[i + 1] if i + 1 < len(b) else 0
                hub_online = hub_state_byte in [0x01, 0xDC]
                break

        result = _base_decoder_dict("valve_hub", rssi_dbm, b)
        result.update({
            "hub_online": hub_online,
            "zones": zones,
            "decoder": "htv0542frf",
            "device_model": "HTV0542FRF",
        })

        _LOGGER.info(debug_with_version("HTV0542FRF decoded: %d zones, hub_online=%s, rssi=%d dBm"),
                     len(zones), hub_online, rssi_dbm)

        return result

    except Exception as e:
        _LOGGER.error(debug_with_version("Error in HTV0542FRF decoder: %s"), e, exc_info=True)
        return {
            "type": "valve_hub",
            "rssi_dbm": 0,
            "raw_bytes": b if 'b' in locals() else [],
            "zones": {},
            "decoder": "htv0542frf_error",
            "error": str(e)
        }
