"""Decoder for generic HomGar valve hub (HTV0540FRF etc)."""
import logging
from ..utils import _parse_homgar_payload, _parse_tlv_payload
from ..validators import _extract_rssi

_LOGGER = logging.getLogger(__name__)

_DP_HUB_STATE = 0x18
_DP_BASE_DURATION = 0x24


def decode_valve_hub(raw: str) -> dict:
    """Decode an irrigation valve hub TLV payload."""
    from ...const import debug_with_version

    try:
        b = _parse_homgar_payload(raw)
        tlv = _parse_tlv_payload(raw)

        zones = {}
        hub_online = False

        if _DP_HUB_STATE in tlv:
            _, hub_state_raw, _ = tlv[_DP_HUB_STATE]
            hub_online = hub_state_raw == 0x01

        for dp, entry in tlv.items():
            type_byte = entry[0]
            if type_byte != 0xD8 or dp <= _DP_HUB_STATE:
                continue
            zone_num = dp - _DP_HUB_STATE
            state_val = entry[1]
            dur_dp = _DP_BASE_DURATION + zone_num
            duration_s = None
            if dur_dp in tlv:
                _, _, dur_bytes = tlv[dur_dp]
                if len(dur_bytes) == 2:
                    duration_s = int.from_bytes(dur_bytes, "little")
            zones[zone_num] = {
                "open": bool(state_val & 0x01) if state_val is not None else None,
                "state_raw": state_val,
                "duration_seconds": duration_s,
            }

        result = {
            "type": "valve_hub",
            "rssi_dbm": _extract_rssi(b) if len(b) > 1 else 0,
            "raw_bytes": b,
            "zones": zones,
            "tlv_raw": tlv,
            "hub_online": hub_online,
            "hub_state_raw": tlv.get(_DP_HUB_STATE, (None, None, None))[1],
            "decoder": "valve_hub_tlv",
        }

        _LOGGER.info(debug_with_version("Valve hub decoded: %d zones, hub_online=%s"), len(zones), hub_online)
        return result

    except Exception as e:
        _LOGGER.error("Valve hub decoder error: %s", e)
        return {
            "type": "valve_hub",
            "rssi_dbm": 0,
            "raw_bytes": [],
            "zones": {},
            "tlv_raw": {},
            "decoder": "valve_hub_error",
            "error": str(e)
        }
