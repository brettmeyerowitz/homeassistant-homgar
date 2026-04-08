"""Decoder for HWS019WRF-V2 Display Hub."""
import logging

_LOGGER = logging.getLogger(__name__)


def decode_hws019wrf_v2(raw: str) -> dict:
    """Decode HWS019WRF-V2 (Display Hub) CSV/semicolon payload."""
    _LOGGER.debug("decode_hws019wrf_v2 called with raw: %r", raw)
    try:
        parts = raw.split(';')
        flags = [int(x) for x in parts[0].split(',') if x.strip().isdigit()]
        readings = {}
        if len(parts) > 1:
            for item in parts[1].split(','):
                item = item.strip()
                if not item:
                    continue
                if '=' in item:
                    key, rest = item.split('=', 1)
                    current_value = rest.split('(')[0].strip() if '(' in rest else rest.strip()
                    readings[key.strip()] = current_value
                elif '(' in item:
                    current_value = item.split('(')[0].strip()
                    if not readings.get('temp'):
                        readings['temp'] = current_value
                    elif not readings.get('humidity'):
                        readings['humidity'] = current_value
        result = {
            "type": "hws019wrf_v2",
            "flags": flags,
            "readings": readings,
            "raw": raw,
        }
        _LOGGER.debug("decode_hws019wrf_v2 result: %r", result)
        return result
    except Exception as ex:
        _LOGGER.warning("Failed to decode HWS019WRF-V2 payload: %s (raw: %r)", ex, raw)
        return {"type": "hws019wrf_v2", "raw": raw, "error": str(ex)}
