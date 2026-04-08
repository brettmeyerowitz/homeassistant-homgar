"""Decoder for HCS008FRF Flow Meter."""
import logging
from ..utils import _parse_homgar_payload
from ..validators import _extract_rssi

_LOGGER = logging.getLogger(__name__)


def decode_hcs008frf(raw: str) -> dict:
    """Decode HCS008FRF (flow meter) using RainPoint TLV protocol."""
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
        "decoder": "rainpoint_tlv",
    }

    try:
        b = _parse_homgar_payload(raw)
        if not b or len(b) < 2:
            return result

        result["rssi_dbm"] = _extract_rssi(b)

        i = 0
        dp_entries = {}
        while i < len(b) - 1:
            dp_id = b[i]
            b9 = b[i + 1]
            type_len = (b9 >> 2) & 31
            if type_len > 0 and i + 2 + type_len <= len(b):
                value_bytes = b[i+2:i+2+type_len]
                if type_len == 4:
                    dp_entries[dp_id] = int.from_bytes(value_bytes, 'little')
                elif type_len == 2:
                    dp_entries[dp_id] = int.from_bytes(value_bytes, 'little')
                elif type_len == 1:
                    dp_entries[dp_id] = value_bytes[0]
                i += 2 + type_len
            else:
                i += 2

        if 255 in dp_entries:
            result["flowcurrentused"] = dp_entries[255] / 1000.0

        result["flowbatt"] = 100

        _LOGGER.info(debug_with_version("HCS008FRF DP entries: %s"), dp_entries)

    except Exception as e:
        _LOGGER.error(debug_with_version("Error in HCS008FRF decoder: %s"), e)
        result["decoder"] = "error"
        result["error"] = str(e)

    return result

