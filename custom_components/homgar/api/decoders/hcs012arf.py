"""Decoder for HCS012ARF Rain Gauge."""
import logging
from ..utils import _le16, _base_decoder_dict, _parse_ascii_sensor_payload, _parse_stats
from ..validators import _validate_payload, _validate_tag, _extract_status_code, _battery_status_to_percent

_LOGGER = logging.getLogger(__name__)


def decode_hcs012arf(raw: str) -> dict:
    """Decode HCS012ARF (rain gauge).

    Supports both US binary format (10#...) and EU ASCII format.
    EU format fields: last_hour_mm10, last_24h_mm10, last_7d_mm10[, total_mm10]
    """
    # EU ASCII format: e.g. "1,0,1;0(0/0/1),0(0/0/1),0(0/0/1),0(0/0/1)"
    # Alternative format: "1,0,1;R=4870(10/20/430)" (single total rain value with R= prefix)
    fields, battery_code, rssi_dbm = _parse_ascii_sensor_payload(raw)
    if fields is not None:
        try:
            # Handle R= prefix format: field like "R=4870(10/20/430)"
            processed_fields = []
            for f in fields:
                if f.startswith('R='):
                    # Extract just the numeric part after R=
                    processed_fields.append(f[2:])  # Remove "R=" prefix
                else:
                    processed_fields.append(f)
            
            # Handle single-field R= format (total rain only) vs multi-field format
            if len(processed_fields) == 1 and fields[0].startswith('R='):
                # Single R= field means total rain only
                total_raw, _, _ = _parse_stats(processed_fields[0])
                last_hour_raw = last_24h_raw = last_7d_raw = 0
            else:
                # Multi-field format: hour, 24h, 7d, total
                last_hour_raw, _, _ = _parse_stats(processed_fields[0]) if len(processed_fields) > 0 else (0, None, None)
                last_24h_raw, _, _ = _parse_stats(processed_fields[1]) if len(processed_fields) > 1 else (0, None, None)
                last_7d_raw, _, _ = _parse_stats(processed_fields[2]) if len(processed_fields) > 2 else (0, None, None)
                total_raw, _, _ = _parse_stats(processed_fields[3]) if len(processed_fields) > 3 else (0, None, None)
            return {
                "type": "rain",
                "rssi_dbm": rssi_dbm or 0,
                "rain_last_hour_mm": (last_hour_raw or 0) / 10.0,
                "rain_last_24h_mm": (last_24h_raw or 0) / 10.0,
                "rain_last_7d_mm": (last_7d_raw or 0) / 10.0,
                "rain_total_mm": (total_raw or 0) / 10.0,
                "battery_percent": None,
                "decoder": "hcs012arf_ascii",
            }
        except Exception as e:
            _LOGGER.warning("HCS012ARF ASCII decode failed: %s (raw: %r)", e, raw)

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

