"""Decoder for HWS019WRF-V2 Display Hub."""
import re
import logging

_LOGGER = logging.getLogger(__name__)

_STATS_RE = re.compile(r'^(\d+)\((\d+)/(\d+)/(\d+)\)')


def _parse_stats(s: str):
    """Parse 'value(max/min/trend)' format. Returns (current, max, min) or (None, None, None)."""
    m = _STATS_RE.match(s.strip())
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return int(s.strip()), None, None
    except (ValueError, TypeError):
        return None, None, None


def _f10_to_c(f10: int) -> float:
    """Convert tenths-of-°F to °C."""
    return round((f10 / 10.0 - 32.0) * 5.0 / 9.0, 1)


def decode_hws019wrf_v2(raw: str) -> dict:
    """Decode HWS019WRF-V2 (Display Hub) payload.

    Payload format (after optional 'battery,rssi;' prefix):
        temp_f10(max/min/trend),humidity%(max/min/trend),P=pressure_pa(max/min/trend)

    Example:
        1,136;781(781/723/1),52(64/50/1),P=10213(10222/10205/1),
    """
    _LOGGER.debug("decode_hws019wrf_v2 raw: %r", raw)
    try:
        result = {"type": "hws019wrf_v2", "raw": raw}

        parts = raw.split(';')
        sensor_part = parts[1] if len(parts) > 1 else parts[0]

        # Parse battery/rssi from prefix if present
        if len(parts) > 1:
            try:
                flag_parts = [x.strip() for x in parts[0].split(',') if x.strip()]
                if len(flag_parts) >= 2:
                    result["battery_status_code"] = int(flag_parts[0])
                    result["rssi_dbm"] = -int(flag_parts[1])
            except (ValueError, IndexError):
                pass

        # Split sensor readings on comma, strip trailing empty entries
        fields = [f.strip() for f in sensor_part.split(',') if f.strip()]

        temp_f = hum = press = None
        temp_f_high = temp_f_low = None
        hum_high = hum_low = None
        press_high = press_low = None

        for field in fields:
            if field.startswith('P='):
                val, hi, lo = _parse_stats(field[2:])
                press = val
                press_high = hi
                press_low = lo
            elif hum is None and temp_f is not None:
                val, hi, lo = _parse_stats(field)
                hum = val
                hum_high = hi
                hum_low = lo
            elif temp_f is None:
                val, hi, lo = _parse_stats(field)
                temp_f = val
                temp_f_high = hi
                temp_f_low = lo

        if temp_f is not None:
            result["temp_current_c"] = _f10_to_c(temp_f)
            if temp_f_high is not None:
                result["temp_high_c"] = _f10_to_c(temp_f_high)
            if temp_f_low is not None:
                result["temp_low_c"] = _f10_to_c(temp_f_low)

        if hum is not None:
            result["humidity_current"] = hum
            if hum_high is not None:
                result["humidity_high"] = hum_high
            if hum_low is not None:
                result["humidity_low"] = hum_low

        if press is not None:
            result["pressure_current_hpa"] = round(press / 100.0, 1)
            if press_high is not None:
                result["pressure_high_hpa"] = round(press_high / 100.0, 1)
            if press_low is not None:
                result["pressure_low_hpa"] = round(press_low / 100.0, 1)

        _LOGGER.debug("decode_hws019wrf_v2 result: %r", result)
        return result

    except Exception as ex:
        _LOGGER.warning("Failed to decode HWS019WRF-V2 payload: %s (raw: %r)", ex, raw)
        return {"type": "hws019wrf_v2", "raw": raw, "error": str(ex)}
