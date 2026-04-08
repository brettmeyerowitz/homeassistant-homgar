"""Decoder for HCS021FRF Moisture + Temp + Lux sensor."""
import logging
from ..utils import _parse_homgar_payload, _le16, _f10_to_c, _base_decoder_dict
from ..validators import _validate_payload, _validate_tag, _extract_rssi, _extract_status_code, _battery_status_to_percent

_LOGGER = logging.getLogger(__name__)


def decode_hcs021frf(raw: str) -> dict:
    """Decode HCS021FRF (moisture + temp + lux)."""
    try:
        if raw.startswith("10#"):
            return _decode_moisture_full_hex(raw)
        elif "," in raw and (";" in raw or "=" in raw):
            return _decode_moisture_full_ascii(raw)
        else:
            raise ValueError(f"Unexpected payload format: {raw}")
    except Exception as e:
        _LOGGER.error("HCS021FRF decoder error: %s", e)
        return {
            "type": "moisture_full",
            "rssi_dbm": 0,
            "raw_bytes": [],
            "decoder": "hcs021frf_error",
            "error": str(e)
        }



def _decode_moisture_full_ascii(raw: str) -> dict:
    from ...const import debug_with_version
    _LOGGER.info(debug_with_version("HCS021FRF ASCII payload: %s"), raw)
    try:
        if ";" not in raw:
            raise ValueError("Invalid ASCII format: missing semicolon")
        header_part, sensor_part = raw.split(";", 1)
        header_parts = header_part.split(",")
        if len(header_parts) < 3:
            raise ValueError("Invalid ASCII header format")
        rssi_raw = int(header_parts[1])
        rssi_dbm = rssi_raw if rssi_raw < 0 else 0
        sensor_parts = sensor_part.split(",")
        if len(sensor_parts) < 3:
            raise ValueError("Invalid ASCII sensor data format")
        temp_raw = int(sensor_parts[0])
        moisture = int(sensor_parts[1])
        lux_data = sensor_parts[2]
        temp_f = temp_raw / 10.0 if temp_raw else 0
        temp_c = (temp_f - 32) * 5 / 9
        if "=" in lux_data:
            lux_parts = lux_data.split("=")
            lux = int(lux_parts[1]) / 10.0 if len(lux_parts) == 2 else 0
        else:
            try:
                lux = int(lux_data) / 10.0
            except ValueError:
                lux = 0
        result = {
            "type": "moisture_full",
            "rssi_dbm": rssi_dbm,
            "raw_bytes": raw.encode('ascii'),
            "moisture_percent": moisture,
            "temperature_c": temp_c,
            "temperature_f10": temp_raw,
            "illuminance_lux": lux,
            "illuminance_raw10": int(lux * 10) if lux else 0,
            "decoder": "hcs021frf_ascii",
        }
        _LOGGER.info(debug_with_version("HCS021FRF ASCII decoded: temp=%.1f°C, moisture=%d%%, lux=%.1f, rssi=%d"),
                     temp_c, moisture, lux, rssi_dbm)
        return result
    except Exception as e:
        _LOGGER.error("HCS021FRF ASCII decoder error: %s", e)
        raise


def _decode_moisture_full_hex(raw: str) -> dict:
    b = _validate_payload(raw, 16)
    if len(b) > 20:
        raise ValueError(f"HCS021FRF payload too long: {len(b)} bytes")
    _validate_tag(b, 5, 0x85, "HCS021FRF")
    rssi = _extract_rssi(b)
    temp_raw_f10 = _le16(b, 6)
    temp_c = _f10_to_c(temp_raw_f10)
    _validate_tag(b, 8, 0x88, "HCS021FRF")
    moisture = b[9]
    _validate_tag(b, 10, 0xC6, "HCS021FRF")
    lux_raw10 = _le16(b, 11)
    lux = lux_raw10 / 10.0
    status_code = _extract_status_code(b, 14, 15) if len(b) >= 16 else 0
    result = _base_decoder_dict("moisture_full", rssi, b)
    result.update({
        "moisture_percent": moisture,
        "temperature_c": temp_c,
        "temperature_f10": temp_raw_f10,
        "illuminance_lux": lux,
        "illuminance_raw10": lux_raw10,
        "battery_status_code": status_code,
        "battery_percent": _battery_status_to_percent(status_code),
        "decoder": "hcs021frf_hex",
    })
    return result
