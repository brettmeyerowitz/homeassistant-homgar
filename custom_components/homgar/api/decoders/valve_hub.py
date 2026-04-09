"""Decoder for generic HomGar valve hub (HTV0540FRF etc)."""
import logging
from ..utils import _parse_homgar_payload, _parse_tlv_payload
from ..validators import _extract_rssi

_LOGGER = logging.getLogger(__name__)

_DP_HUB_STATE = 0x18
_DP_BASE_DURATION = 0x24
_DP_BATTERY = 0xFE


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

        # Collect all D8-type DPs above hub state as zone state DPs, sorted
        zone_state_dps = sorted(
            dp for dp, entry in tlv.items()
            if entry[0] == 0xD8 and dp > _DP_HUB_STATE
        )
        for zone_num, zone_dp in enumerate(zone_state_dps, 1):
            state_val = tlv[zone_dp][1]
            # Duration is stored 8 DPs above the zone state DP (B7 type, 4 bytes LE)
            dur_dp = zone_dp + 8
            duration_s = None
            if dur_dp in tlv and tlv[dur_dp][0] == 0xB7:
                _, _, dur_bytes = tlv[dur_dp]
                if len(dur_bytes) == 4:
                    duration_s = int.from_bytes(dur_bytes, "little")
            # Also try AD-type duration (2 bytes LE) at zone_dp+12
            if duration_s is None:
                dur_dp2 = zone_dp + 12
                if dur_dp2 in tlv and tlv[dur_dp2][0] == 0xAD:
                    _, _, dur_bytes = tlv[dur_dp2]
                    if len(dur_bytes) == 2:
                        duration_s = int.from_bytes(dur_bytes, "little")
            zones[zone_num] = {
                "open": bool(state_val & 0x01) if state_val is not None else None,
                "state_raw": state_val,
                "duration_seconds": duration_s,
            }

        battery_percent = None
        if _DP_BATTERY in tlv:
            _, batt_raw, batt_bytes = tlv[_DP_BATTERY]
            if batt_bytes and len(batt_bytes) >= 1:
                batt_val = batt_bytes[0]
                if batt_val == 0x0F:
                    battery_percent = 100
                elif batt_val <= 100:
                    battery_percent = batt_val

        result = {
            "type": "valve_hub",
            "rssi_dbm": _extract_rssi(b) if len(b) > 1 else 0,
            "raw_bytes": b,
            "zones": zones,
            "tlv_raw": tlv,
            "hub_online": hub_online,
            "hub_state_raw": tlv.get(_DP_HUB_STATE, (None, None, None))[1],
            "battery_percent": battery_percent,
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
