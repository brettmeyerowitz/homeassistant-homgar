"""Decoder for HCS026FRF Moisture (Simple) sensor."""
import logging
from ..utils import _base_decoder_dict
from ..validators import _validate_payload, _validate_tag, _extract_rssi, _extract_status_code, _battery_status_to_percent

_LOGGER = logging.getLogger(__name__)


def decode_hcs026frf(raw: str) -> dict:
    """Decode HCS026FRF (moisture-only) payload."""
    b = _validate_payload(raw, 9)
    _validate_tag(b, 5, 0x88, "HCS026FRF")

    rssi = _extract_rssi(b)
    moisture = b[6]
    status_code = _extract_status_code(b, 7, 8)

    result = _base_decoder_dict("moisture_simple", rssi, b)
    result.update({
        "moisture_percent": moisture,
        "battery_status_code": status_code,
        "battery_percent": _battery_status_to_percent(status_code),
    })
    return result

