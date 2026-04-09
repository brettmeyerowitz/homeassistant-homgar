"""Decoder for HCS014ARF Temperature/Humidity sensor."""
import logging
from ..utils import _parse_homgar_payload, _le16, _f10_to_c, _parse_ascii_sensor_payload, _parse_stats
from ..validators import _extract_rssi, _extract_status_code, _battery_status_to_percent

_LOGGER = logging.getLogger(__name__)


def decode_hcs014arf(raw: str) -> dict:
    """Decode HCS014ARF (Temperature/Humidity) sensor.

    Supports both US binary format (10#...) and EU ASCII format (battery,rssi;temp,hum).
    """
    from ...const import debug_with_version

    _LOGGER.debug(debug_with_version("Decoding HCS014ARF: %s"), raw)

    # EU ASCII format: e.g. "1,0,1;798(798/798/1),30(30/30/1)"
    fields, battery_code, rssi_dbm = _parse_ascii_sensor_payload(raw)
    if fields is not None:
        try:
            temp_f10, _, _ = _parse_stats(fields[0]) if len(fields) > 0 else (None, None, None)
            hum, _, _ = _parse_stats(fields[1]) if len(fields) > 1 else (None, None, None)
            temp_c = round(_f10_to_c(temp_f10), 1) if temp_f10 is not None else None
            return {
                "type": "temphum",
                "rssi_dbm": rssi_dbm or 0,
                "tempcurrent": temp_c,
                "humiditycurrent": hum,
                "battery_percent": None,
                "decoder": "hcs014arf_ascii",
            }
        except Exception as e:
            _LOGGER.warning("HCS014ARF ASCII decode failed: %s (raw: %r)", e, raw)

    try:
        b = _parse_homgar_payload(raw)
        if not b or len(b) < 18:
            return {
                "type": "temphum",
                "rssi_dbm": 0,
                "tempcurrent": None,
                "humiditycurrent": None,
                "battery_percent": None,
                "decoder": "hcs014arf_error",
            }

        # RSSI from byte 1 (signed: values >= 128 are negative dBm)
        rssi_dbm = _extract_rssi(b)

        # Temperature from bytes 10-11 (little-endian tenths of °F)
        temp_raw_f10 = _le16(b, 10)
        temp_c = _f10_to_c(temp_raw_f10)

        # Humidity from byte 13
        humidity = b[13]

        # Battery status from bytes 17-18 (FF 0F = 100%)
        status_code = _extract_status_code(b, 17, 18) if len(b) >= 19 else 0
        battery = _battery_status_to_percent(status_code)

        result = {
            "type": "temphum",
            "rssi_dbm": rssi_dbm,
            "tempcurrent": round(temp_c, 1),
            "humiditycurrent": humidity,
            "battery_percent": battery,
            "decoder": "hcs014arf",
        }

        _LOGGER.info(debug_with_version("HCS014ARF decoded: temp=%.1f°C, humidity=%d%%, rssi=%d dBm"),
                     temp_c, humidity, rssi_dbm)

        return result

    except Exception as e:
        _LOGGER.error(debug_with_version("Error in HCS014ARF decoder: %s"), e, exc_info=True)
        return {
            "type": "temphum",
            "rssi_dbm": 0,
            "tempcurrent": None,
            "humiditycurrent": None,
            "battery_percent": None,
            "decoder": "hcs014arf_error",
        }
