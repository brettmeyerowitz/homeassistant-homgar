"""Decoder for HCS0528ARF Pool Temperature sensor."""
import logging
from ..utils import _parse_homgar_payload, _le16, _f10_to_c, _base_decoder_dict
from ..validators import _extract_status_code, _battery_status_to_percent

_LOGGER = logging.getLogger(__name__)


def decode_hcs0528arf(raw: str) -> dict:
    """Decode HCS0528ARF (pool temperature sensor) payload.

    Byte layout (after 10# prefix):
    - Bytes 0:    RSSI (negate for dBm)
    - Bytes 1-2:  Low temperature (LE16, tenths of °F)
    - Bytes 3-4:  High temperature (LE16, tenths of °F)
    - Bytes 10-11: Current temperature (LE16, tenths of °F)
    - Bytes 12-13: Battery status (0xFF 0x0F = 100%)
    """
    from ...const import debug_with_version

    _LOGGER.debug(debug_with_version("Decoding HCS0528ARF: %s"), raw)

    try:
        b = _parse_homgar_payload(raw)

        if not b or len(b) < 12:
            raise ValueError(f"HCS0528ARF payload too short: {len(b) if b else 0} bytes")

        temp_current_raw_f10 = _le16(b, 10)
        temp_current_c = _f10_to_c(temp_current_raw_f10)

        temp_high_raw_f10 = _le16(b, 3)
        temp_high_c = _f10_to_c(temp_high_raw_f10)

        temp_low_raw_f10 = _le16(b, 1)
        temp_low_c = _f10_to_c(temp_low_raw_f10)

        status_code = _extract_status_code(b, 12, 13) if len(b) >= 14 else 0
        rssi_dbm = -b[0] if b[0] > 0 else 0

        result = _base_decoder_dict("pool", rssi_dbm, b)
        result.update({
            "tempcurrent": round(temp_current_c, 1),
            "temphigh": round(temp_high_c, 1),
            "templow": round(temp_low_c, 1),
            "battery_status_code": status_code,
            "battery_percent": _battery_status_to_percent(status_code),
            "decoder": "hcs0528arf",
        })

        _LOGGER.info(debug_with_version("HCS0528ARF decoded: current=%.1f°C, high=%.1f°C, low=%.1f°C, rssi=%d dBm"),
                     temp_current_c, temp_high_c, temp_low_c, rssi_dbm)

        return result

    except Exception as e:
        _LOGGER.error(debug_with_version("Error in HCS0528ARF decoder: %s"), e, exc_info=True)
        return {
            "type": "pool",
            "rssi_dbm": 0,
            "raw_bytes": b if 'b' in locals() else [],
            "decoder": "hcs0528arf_error",
            "error": str(e)
        }

