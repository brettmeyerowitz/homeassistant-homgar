"""Decoder for HTV213FRF / HTV245FRF valve hub."""
import logging
from ..utils import _parse_homgar_payload, _parse_tlv_payload
from ..validators import _extract_rssi

_LOGGER = logging.getLogger(__name__)


def decode_htv213frf(raw: str) -> dict:
    """Decode HTV213FRF/HTV245FRF valve hub payload."""
    try:
        if raw.startswith("11#"):
            return _decode_htv213frf_hex(raw)
        elif "," in raw and (";" in raw or "|" in raw):
            return _decode_htv213frf_ascii(raw)
        else:
            raise ValueError(f"Unexpected payload format: {raw}")
    except Exception as e:
        _LOGGER.error("HTV213FRF decoder error: %s", e)
        return {
            "type": "valve_hub",
            "rssi_dbm": 0,
            "raw_bytes": [],
            "zones": {},
            "tlv_raw": {},
            "decoder": "htv213frf_error",
            "error": str(e)
        }


def _decode_htv213frf_ascii(raw: str) -> dict:
    from ...const import debug_with_version
    _LOGGER.info(debug_with_version("HTV213FRF ASCII payload: %s"), raw)
    try:
        if ";" not in raw:
            raise ValueError("Invalid ASCII format: missing semicolon")
        header_part, zone_part = raw.split(";", 1)
        header_parts = header_part.split(",")
        if len(header_parts) < 3:
            raise ValueError("Invalid ASCII header format")
        rssi_raw = int(header_parts[1])
        rssi_dbm = rssi_raw if rssi_raw < 0 else 0
        zone_sections = zone_part.split("|")
        zone_mapping = {}
        sequential_zone = 1
        for zone_data in zone_sections:
            if not zone_data.strip():
                continue
            zone_parts = zone_data.split(",")
            if len(zone_parts) < 6:
                continue
            state = int(zone_parts[1])
            duration = int(zone_parts[2]) if len(zone_parts) > 2 else 0
            zone_mapping[sequential_zone] = {
                'raw_zone_id': int(zone_parts[0]),
                'open': bool(state & 0x01),
                'duration_seconds': duration,
                'raw_ascii_data': zone_data
            }
            sequential_zone += 1
        result = {
            "type": "valve_hub",
            "rssi_dbm": rssi_dbm,
            "raw_bytes": raw.encode('ascii'),
            "zones": zone_mapping,
            "tlv_raw": {},
            "hub_online": True,
            "hub_state_raw": "ascii_format",
            "decoder": "htv213frf_ascii",
        }
        _LOGGER.info(debug_with_version("HTV213FRF ASCII decoded: %d zones, rssi=%d"), len(zone_mapping), rssi_dbm)
        return result
    except Exception as e:
        _LOGGER.error("HTV213FRF ASCII decoder error: %s", e)
        raise


def _decode_htv213frf_hex(raw: str) -> dict:
    from ...const import debug_with_version
    from .valve_hub import decode_valve_hub
    try:
        b = _parse_homgar_payload(raw)
        zones = {}
        try:
            tlv = _parse_tlv_payload(raw)
        except Exception:
            tlv = {}

        if tlv:
            return decode_valve_hub(raw)

        zone_data = []
        max_zones = 2
        i = 4
        while i < len(b) - 6 and len(zone_data) < max_zones:
            zone_id = b[i]
            state = b[i + 1]
            if b[i + 2] == 0x00 and b[i + 5] == 0x00:
                duration = (b[i + 3] << 8) | b[i + 4]
                zone_data.append({'zone_id': zone_id, 'state': state, 'duration': duration, 'position': i})
                i += 6
            else:
                i += 1

        zone_mapping = {}
        for idx, zone in enumerate(zone_data, 1):
            zone_mapping[idx] = {
                'raw_zone_id': zone['zone_id'],
                'open': bool(zone['state'] & 0x01),
                'duration_seconds': zone['duration'],
                'raw_position': zone['position']
            }

        hub_online = False
        if len(b) >= 28 and b[26] == 0x18:
            hub_online = b[27] in [0x01, 0xDC]

        result = {
            "type": "valve_hub",
            "rssi_dbm": _extract_rssi(b) if len(b) > 1 else 0,
            "raw_bytes": b,
            "zones": zone_mapping,
            "tlv_raw": tlv,
            "hub_online": hub_online,
            "hub_state_raw": b[27] if len(b) > 27 else None,
            "decoder": "htv213frf_custom",
        }
        return result
    except Exception as e:
        _LOGGER.error("HTV213FRF decoder error: %s", e)
        return {
            "type": "valve_hub",
            "rssi_dbm": 0,
            "raw_bytes": [],
            "zones": {},
            "tlv_raw": {},
            "decoder": "htv213frf_error",
            "error": str(e)
        }

