"""Decoder for HCS0565ARF Pool Temperature sensor."""
import logging
from ..utils import _parse_homgar_payload, _le16, _f10_to_c
from ..validators import _extract_rssi, _battery_status_to_percent

_LOGGER = logging.getLogger(__name__)


def decode_hcs0565arf(raw: str) -> dict:
    """Decode HCS0565ARF pool temperature sensor."""
    from ...const import debug_with_version

    _LOGGER.debug(debug_with_version("Decoding HCS0565ARF: %s"), raw)

    result = {
        "type": "pool",
        "device_model": "HCS0565ARF",
        "tempcurrent": None,
        "temphigh": None,
        "templow": None,
        "rssi_dbm": None,
        "battery_percent": None,
        "decoder": "hcs0565arf",
    }

    try:
        b = _parse_homgar_payload(raw)

        if len(b) < 18:
            _LOGGER.warning(debug_with_version("HCS0565ARF payload too short: %d bytes"), len(b))
            return result

        result["rssi_dbm"] = _extract_rssi(b)

        temp_f10 = _le16(b, 3)
        result["tempcurrent"] = round(_f10_to_c(temp_f10), 1)

        if b[12] == 0xFF and b[13] == 0x0F:
            result["battery_percent"] = 100
        else:
            battery_status = (b[12] << 8) | b[13]
            result["battery_percent"] = _battery_status_to_percent(battery_status)

    except Exception as e:
        _LOGGER.error(debug_with_version("Error in HCS0565ARF decoder: %s"), e)
        result["decoder"] = "error"
        result["error"] = str(e)

    return result
