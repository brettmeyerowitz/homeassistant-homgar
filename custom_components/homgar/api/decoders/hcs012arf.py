"""Decoder for HCS012ARF Rain Gauge."""
import logging
from ..utils import _le16, _base_decoder_dict
from ..validators import _validate_payload, _validate_tag, _extract_status_code, _battery_status_to_percent

_LOGGER = logging.getLogger(__name__)


def decode_hcs012arf(raw: str) -> dict:
    """Decode HCS012ARF (rain gauge)."""
    b = _validate_payload(raw, 24)

    if not (b[3] == 0xFD and b[4] == 0x04):
        raise ValueError("HCS012ARF: Missing FD 04 at [3:5]")
    if not (b[7] == 0xFD and b[8] == 0x05):
        raise ValueError("HCS012ARF: Missing FD 05 at [7:9]")
    if not (b[11] == 0xFD and b[12] == 0x06):
        raise ValueError("HCS012ARF: Missing FD 06 at [11:13]")
    _validate_tag(b, 17, 0x97, "HCS012ARF")

    last_hour_raw10 = _le16(b, 5)
    last_24h_raw10 = _le16(b, 9)
    last_7d_raw10 = _le16(b, 13)
    total_raw10 = _le16(b, 18)

    status_code = _extract_status_code(b, 22, 23)

    result = _base_decoder_dict("rain", 0, b)
    result.update({
        "rain_last_hour_mm": last_hour_raw10 / 10.0,
        "rain_last_24h_mm": last_24h_raw10 / 10.0,
        "rain_last_7d_mm": last_7d_raw10 / 10.0,
        "rain_total_mm": total_raw10 / 10.0,
        "rain_last_hour_raw10": last_hour_raw10,
        "rain_last_24h_raw10": last_24h_raw10,
        "rain_last_7d_raw10": last_7d_raw10,
        "rain_total_raw10": total_raw10,
        "battery_status_code": status_code,
        "battery_percent": _battery_status_to_percent(status_code),
    })
    return result

