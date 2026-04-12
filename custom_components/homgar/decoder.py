"""
decoder.py — Product-model-driven HomGar/RainPoint payload decoder.

Ported from docs/java-decoders/decode_pm.py.
Loads device definitions from data/product_models.json (shipped with the
integration) and decodes any statusParam payload without per-model code.

Public API:
    decode_payload(model, status_param) -> dict
    get_model_info(model) -> dict | None
"""
from __future__ import annotations

import json
import logging
import struct
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"
_MODELS_FILE = _DATA_DIR / "product_models.json"


# ---------------------------------------------------------------------------
# Model registry — loaded eagerly at import time (import runs in executor,
# never inside the HA event loop, so synchronous open() is safe here).
# ---------------------------------------------------------------------------

def _build_model_registry() -> dict[str, dict]:
    try:
        with open(_MODELS_FILE) as f:
            data = json.load(f)
    except Exception as exc:
        _LOGGER.error("Failed to load product_models.json: %s", exc)
        return {}
    result: dict[str, dict] = {}
    for m in data["data"]["models"]:
        key = m["model"]
        result[key] = m
        dm = m.get("displayModel", "")
        if dm and dm != key and dm not in result:
            result[dm] = m
    _LOGGER.debug("Loaded %d models from product_models.json", len(result))
    return result


_MODELS: dict[str, dict] = _build_model_registry()


def _load_models() -> dict[str, dict]:
    """Return the eagerly-loaded model registry."""
    return _MODELS


def get_model_info(model: str) -> dict | None:
    """Return the product_models.json dict for a model, or None if not found."""
    models = _load_models()
    for k, v in models.items():
        if k.upper() == model.upper():
            return v
    return None


def get_valve_ports(model: str) -> list[int]:
    """
    Return a list of port numbers that have CTL_WATER or CTL_BT_WATER entries.
    Empty list means the model is not a valve/controllable device.
    Used by valve.py to determine how many ValveEntity objects to create.

    Two layouts are handled:
      - Per-port: CTL_WATER dp entries each have dpPort > 0 (e.g. HTV113FRF).
        Returns the explicit dpPort values.
      - Bitmask hub: single CTL_WATER with dpPort=0 and portNumber > 1
        (e.g. HIC801W). Returns [1, 2, ..., portNumber].
    """
    info = get_model_info(model)
    if not info:
        return []
    per_port = [
        dp["dpPort"] for dp in info.get("dp", [])
        if dp.get("identity") in ("CTL_WATER", "CTL_BT_WATER")
        and dp.get("dpPort", 0) > 0
    ]
    if per_port:
        return per_port
    has_global_ctl = any(
        dp.get("identity") in ("CTL_WATER", "CTL_BT_WATER")
        and dp.get("dpPort", 0) == 0
        for dp in info.get("dp", [])
    )
    port_number = info.get("portNumber", 0) or 0
    if has_global_ctl and port_number > 1:
        return list(range(1, port_number + 1))
    return []


def _build_dp_index(model_dict: dict) -> dict[int, dict]:
    return {dp["dpId"]: dp for dp in model_dict.get("dp", [])}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DP_CODE: dict[int, str] = {
    0: "CHG", 1: "RAIN", 2: "ALARM", 3: "CHECK", 4: "OTHER",
    8: "RM_TIME", 9: "TEM", 10: "RH", 11: "PH", 12: "ATMOS",
    13: "TOTAL_RAIN", 14: "V_FLOW", 15: "LAST_USAGE", 16: "CURRENT",
    17: "POWER", 18: "ENERGY", 19: "DURATION", 20: "WATER_TOTAL",
    21: "EVENT_TIME", 22: "TREND", 23: "SENSOR_F", 24: "V_WIND",
    25: "ILLUMINANCE", 26: "TOTAL_TODAY", 27: "CO2", 28: "PM25",
    29: "VOLTAGE", 30: "WK_STATE", 31: "BAT", 32: "RSSI",
    33: "MAX_TEM", 34: "MAX_RH", 35: "MAX_STATE_MOS", 36: "MAX_WIND",
    37: "WATER_ZONES", 38: "TS_DET", 39: "STA_VALVE", 40: "STA_JOB",
    41: "STA_CALL", 42: "STA_WATER_PS", 43: "HOUR_RAIN", 44: "DAY_RAIN",
    45: "WEEK_RAIN", 46: "STA_CUR_FLOW", 47: "MAX_CO2", 48: "MAX_PM25",
    49: "STA_LAST_DURATION", 50: "STA_OTHER_TOTAL", 51: "STA_RSSI2",
}

_WORK_MODES: dict[int, str] = {
    0: "idle", 1: "irrigation", 2: "mist", 3: "cycle", 7: "soak",
}

# RF soil-probe sensors that encode volumetric water content in STA_RH.
# All other models with STA_RH are genuine air-humidity sensors.
SOIL_MOISTURE_MODELS: frozenset[str] = frozenset({
    "HCS003FRF",
    "HCS005FRF",
    "HCS021FRF",
    "HCS024FRF",
    "HCS024FRF-V1",
    "HCS026FRF",
    "HCS044FRF",
    "HCS666FRF",
    "HCS666FRF-X",
    "HCS666RFR-P",
    "HCS999FRF",
    "HCS999FRF-P",
})


# ---------------------------------------------------------------------------
# TLV parser
# ---------------------------------------------------------------------------

def _parse_prefix(status_param: str) -> tuple[str, bool]:
    if "#" in status_param:
        z8 = status_param[1:2] == "1"
        status_param = status_param[3:]
    else:
        z8 = False
    comma = status_param.find(",")
    if comma != -1:
        status_param = status_param[:comma]
    return status_param.upper(), z8


def _hex_to_bytes(hex_str: str) -> list[int]:
    n = len(hex_str) // 2
    return [int(hex_str[i * 2: i * 2 + 2], 16) & 0xFF for i in range(n)]


def _parse_tlv(data: list[int], z8: bool) -> list[dict]:
    entries = []
    i = 0
    n = len(data)
    while i < n:
        e: dict = {"dp_id": 0, "type_code": -1, "name": "UNKNOWN",
                   "type_len": 0, "type_value": []}
        if z8:
            e["dp_id"] = data[i]; i += 1
        if i >= n:
            break
        h = data[i]
        if (h >> 7) & 1 == 0:
            e["type_code"] = (h >> 4) & 7
            e["type_len"] = 1
            e["type_value"] = [h]
            i += 1
        else:
            i13 = (h >> 2) & 31
            b10 = h & 3
            e["type_len"] = b10 + 1
            copy = b10 + 2
            if i13 <= 30:
                e["type_code"] = i13 + 8
                e["type_value"] = data[i: i + copy]
                i += copy
            else:
                i += 1
                if i >= n:
                    break
                e["type_code"] = (data[i] & 0xFF) + 39
                e["type_value"] = data[i: i + copy]
                i += copy
        e["name"] = _DP_CODE.get(e["type_code"], f"UNKNOWN_{e['type_code']}")
        entries.append(e)
    if z8:
        entries = [e for e in entries if e["dp_id"] != 0]
    return entries


def _is_legacy(status_param: str) -> bool:
    sp = status_param.strip()
    if len(sp) >= 3 and sp[0].isdigit() and sp[1].isdigit() and sp[2] == "#":
        return False
    return True


# ---------------------------------------------------------------------------
# Legacy payload parser
# ---------------------------------------------------------------------------

def _parse_legacy(status_param: str) -> dict:
    sp = status_param.strip()
    parts = sp.split(";", 1)
    p1 = parts[0].split(",") if parts else []
    p2_raw = parts[1] if len(parts) > 1 else ""
    p2 = p2_raw.split(",") if p2_raw else []

    def p1i(idx):
        try:
            return int(p1[idx])
        except (IndexError, ValueError):
            return None

    def p2i(idx):
        try:
            v = p2[idx]
            if "(" in v:
                v = v[:v.index("(")]
            return int(v)
        except (IndexError, ValueError):
            return None

    def named(key):
        prefix = key + "="
        for tok in p2:
            if tok.strip().startswith(prefix):
                return tok.strip()[len(prefix):]
        return None

    def parse_named_value(key):
        raw = named(key)
        if raw is None:
            return None, []
        if "(" in raw and ")" in raw:
            base = raw[:raw.index("(")]
            inner = raw[raw.index("(") + 1:raw.index(")")].split("/")
        else:
            base, inner = raw, []
        return base, inner

    out: dict = {}
    out["_p1_online"] = p1i(0)
    out["_p1_bat_or_rssi"] = p1i(1)
    out["_p1_rssi"] = p1i(2)
    out["_p1_charge"] = p1i(3)

    t_base, t_inner = parse_named_value("T")
    if t_base is not None:
        try:
            out["_leg_temp_raw"] = int(t_base)
            out["_leg_temp_max_raw"] = int(t_inner[0]) if len(t_inner) > 0 else None
            out["_leg_temp_min_raw"] = int(t_inner[1]) if len(t_inner) > 1 else None
            out["_leg_temp_trend"] = int(t_inner[2]) if len(t_inner) > 2 else None
        except (ValueError, TypeError):
            pass

    h_base, h_inner = parse_named_value("H")
    if h_base is not None:
        try:
            out["_leg_rh"] = int(h_base)
            out["_leg_rh_max"] = int(h_inner[0]) if len(h_inner) > 0 else None
            out["_leg_rh_min"] = int(h_inner[1]) if len(h_inner) > 1 else None
        except (ValueError, TypeError):
            pass

    p_base, p_inner = parse_named_value("P")
    if p_base is not None:
        try:
            out["_leg_pressure_raw"] = int(p_base)
            out["_leg_pressure_trend"] = int(p_inner[0]) if len(p_inner) > 0 else None
            out["_leg_pressure_min_raw"] = int(p_inner[1]) if len(p_inner) > 1 else None
            out["_leg_pressure_max_raw"] = int(p_inner[2]) if len(p_inner) > 2 else None
        except (ValueError, TypeError):
            pass

    c_raw = named("C")
    if c_raw and len(c_raw) >= 8:
        try:
            hi = int(c_raw[0:4], 16)
            co2_val = ((hi << 8) | (hi >> 8)) & 0xFFFF
            out["_leg_co2"] = None if co2_val == 0xFFFF else co2_val
            hi2 = int(c_raw[4:8], 16)
            co2_warn = ((hi2 << 8) | (hi2 >> 8)) & 0xFFFF
            out["_leg_co2_warning"] = None if co2_warn == 0xFFFF else co2_warn
        except (ValueError, TypeError):
            pass

    r_base, r_inner = parse_named_value("R")
    if r_base is not None:
        try:
            out["_leg_rain_total_raw"] = int(r_base)
            out["_leg_rain_1h_raw"] = int(r_inner[0]) if len(r_inner) > 0 else None
            out["_leg_rain_24h_raw"] = int(r_inner[1]) if len(r_inner) > 1 else None
            out["_leg_rain_7d_raw"] = int(r_inner[2]) if len(r_inner) > 2 else None
        except (ValueError, TypeError):
            pass

    v_base, v_inner = parse_named_value("V")
    if v_base is not None:
        try:
            out["_leg_wind_raw"] = int(v_base)
            out["_leg_wind_trend"] = int(v_inner[0]) if len(v_inner) > 0 else None
            out["_leg_wind_min_raw"] = int(v_inner[1]) if len(v_inner) > 1 else None
            out["_leg_wind_max_raw"] = int(v_inner[2]) if len(v_inner) > 2 else None
        except (ValueError, TypeError):
            pass

    # Positional temp/humidity fallback (HCS014ARF, HWS019WRF-V2 etc.)
    # These use p2[0]=temp_raw, p2[1]=rh when no named T=/H= keys are present.
    if "_leg_temp_raw" not in out and p2i(0) is not None:
        out["_leg_temp_raw"] = p2i(0)
        try:
            t_tok = p2[0]
            if "(" in t_tok and ")" in t_tok:
                inner = t_tok[t_tok.index("(") + 1:t_tok.index(")")].split("/")
                out["_leg_temp_max_raw"] = int(inner[0]) if len(inner) > 0 else None
                out["_leg_temp_min_raw"] = int(inner[1]) if len(inner) > 1 else None
        except (IndexError, ValueError):
            pass
    if "_leg_rh" not in out and p2i(1) is not None:
        out["_leg_rh"] = p2i(1)
        try:
            h_tok = p2[1]
            if "(" in h_tok and ")" in h_tok:
                inner = h_tok[h_tok.index("(") + 1:h_tok.index(")")].split("/")
                out["_leg_rh_max"] = int(inner[0]) if len(inner) > 0 else None
                out["_leg_rh_min"] = int(inner[1]) if len(inner) > 1 else None
        except (IndexError, ValueError):
            pass

    out["_leg_last_water_cons_raw"] = p2i(1)
    out["_leg_cur_water_raw"] = p2i(2)
    out["_leg_cur_duration"] = p2i(3)
    out["_leg_last_usage_raw"] = p2i(4)
    out["_leg_last_duration"] = p2i(5)
    out["_leg_today_water_raw"] = p2i(6)
    out["_leg_total_water_raw"] = p2i(7)
    out["_leg_reset_water_raw"] = p2i(8)

    out["_leg_port_sections"] = [s.strip() for s in p2_raw.split("|")]
    return out


def _leg_temp_display(raw, temp_unit):
    if raw is None:
        return None
    if raw == 32767:
        return "HH"
    if raw == -32768:
        return "LL"
    if raw in (32766, 50000):
        return None
    return _temp_from_raw(raw, temp_unit)


_WORK_MODE_TO_VALVE_STATE = {
    0: "idle",
    1: "irrigation",
    2: "mist",
    3: "cycle",
    7: "soak",
}


def _decode_legacy_port_section(section: str, unit: str) -> dict:
    """Decode one pipe-separated port section from a legacy multi-port valve payload.

    Field layout (comma-separated within the section):
      [0] valve_state_code  — integer; lower nibble = work mode
                              0=idle, 1=irrigation, 2=mist, 3=cycle, 7=soak
                              The app checks != 0 for is_watering
      [1] duration_minutes  — current session duration in minutes
      [2] unknown
      [3] event_time        — Unix timestamp (last event)
      [4] total_duration    — total programmed duration in seconds
      [5] unknown
    """
    result: dict = {}
    fields = section.split(",")

    def fi(idx):
        try:
            v = fields[idx].strip()
            if "(" in v:
                v = v[:v.index("(")]
            return int(v)
        except (IndexError, ValueError):
            return None

    wk_raw = fi(0)
    if wk_raw is not None:
        wk = wk_raw & 0x0F
        result["valve_state"] = _WORK_MODE_TO_VALVE_STATE.get(wk, str(wk))
        result["is_watering"] = wk != 0

    dur_min = fi(1)
    if dur_min is not None:
        result["current_session_duration"] = dur_min * 60

    ev_time = fi(3)
    if ev_time is not None and ev_time > 1_000_000_000:
        result["event_time_raw"] = ev_time

    return result


def _decode_legacy_fields(leg: dict, unit: str, temp_unit: str,
                          port_number: int = 1) -> dict:
    result: dict = {}

    if "_leg_temp_raw" in leg:
        v = _leg_temp_display(leg["_leg_temp_raw"], temp_unit)
        if v is not None:
            result["temperature"] = v

    if "_leg_rh" in leg and leg["_leg_rh"] is not None:
        result["humidity"] = leg["_leg_rh"]

    if "_leg_pressure_raw" in leg and leg["_leg_pressure_raw"] is not None:
        result["air_pressure"] = round(leg["_leg_pressure_raw"] / 10.0, 1)

    if "_leg_co2" in leg and leg["_leg_co2"] is not None:
        result["carbon_dioxide"] = leg["_leg_co2"]

    if "_leg_rain_total_raw" in leg:
        def _mm(v):
            return None if v is None else round(v / 10.0, 1)
        result["precipitation_total"] = _mm(leg["_leg_rain_total_raw"])
        r1h = _mm(leg.get("_leg_rain_1h_raw"))
        r24h = _mm(leg.get("_leg_rain_24h_raw"))
        r7d = _mm(leg.get("_leg_rain_7d_raw"))
        if r1h is not None:
            result["precipitation_1h"] = r1h
        if r24h is not None:
            result["precipitation_24h"] = r24h
        if r7d is not None:
            result["precipitation_7d"] = r7d

    if "_leg_wind_raw" in leg and leg["_leg_wind_raw"] is not None:
        result["wind_speed"] = round(leg["_leg_wind_raw"] / 10.0, 1)

    if leg.get("_leg_cur_water_raw") is not None:
        result["current_water_volume"] = _vol(leg["_leg_cur_water_raw"], unit)
    if leg.get("_leg_last_usage_raw") is not None:
        result["last_water_volume"] = _vol(leg["_leg_last_usage_raw"], unit)
    if leg.get("_leg_today_water_raw") is not None:
        result["today_water_volume"] = _vol(leg["_leg_today_water_raw"], unit)
    if leg.get("_leg_total_water_raw") is not None:
        result["total_water_volume"] = _vol(leg["_leg_total_water_raw"], unit)
    if leg.get("_leg_cur_duration") is not None:
        result["current_session_duration"] = leg["_leg_cur_duration"]

    bat_or_rssi = leg.get("_p1_bat_or_rssi")
    rssi = leg.get("_p1_rssi")
    if bat_or_rssi is not None:
        if bat_or_rssi < 0:
            result["signal_strength"] = bat_or_rssi
        else:
            result["battery_level"] = bat_or_rssi
    if rssi is not None:
        result["signal_strength"] = rssi

    port_sections = leg.get("_leg_port_sections", [])
    if port_number > 1 and len(port_sections) >= port_number:
        for p in range(1, port_number + 1):
            section = port_sections[p - 1]
            if section:
                result[f"port_{p}"] = _decode_legacy_port_section(section, unit)

    return result


# ---------------------------------------------------------------------------
# Unit and math helpers
# ---------------------------------------------------------------------------

def _vol(raw: int, unit: str) -> float:
    if unit == "L":
        return round(raw / 10.0, 2)
    v = (raw / 10.0) * 0.2642
    return float(Decimal(str(v)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _temp_from_raw(raw: float, temp_unit: str) -> float:
    f_val = raw / 10.0
    if temp_unit == "F":
        return round(f_val, 1)
    return round((f_val - 32.0) * 5.0 / 9.0, 1)


# ---------------------------------------------------------------------------
# TLV field extractors
# ---------------------------------------------------------------------------

def _le_int(tlv: dict) -> int:
    tlen = tlv["type_len"]
    payload = tlv["type_value"][1:1 + tlen]
    buf = bytes(payload + [0] * (8 - len(payload)))
    return struct.unpack_from("<q", buf)[0]


def _entries_for_port(entries: list[dict], dp_index: dict[int, dict],
                      port: int | None) -> list[dict]:
    if not dp_index or port is None:
        return entries
    result = []
    for e in entries:
        dp = dp_index.get(e["dp_id"])
        if dp is None:
            result.append(e)
        elif dp["dpPort"] == port or dp["dpPort"] == 0:
            result.append(e)
    return result


def _find_by_identity(entries: list[dict], dp_index: dict[int, dict],
                      identity: str, port: int | None = None) -> dict | None:
    for e in entries:
        dp = dp_index.get(e["dp_id"])
        if dp and dp.get("identity") == identity:
            if port is None or dp["dpPort"] == port or dp["dpPort"] == 0:
                return e
    return None


def _find_by_name(entries: list[dict], name: str) -> dict | None:
    for e in entries:
        if e["name"] == name:
            return e
    return None


def _find_entry(entries, dp_index, identity, dp_code_name, port=None):
    e = _find_by_identity(entries, dp_index, identity, port)
    if e is None:
        e = _find_by_name(entries, dp_code_name)
    return e


def _dec_rssi(entries, dp_index):
    e = _find_entry(entries, dp_index, "STA_RSSI", "RSSI")
    if e is None or len(e["type_value"]) < 2:
        e = _find_by_identity(entries, dp_index, "STA_RSSI2")
        if e is None or len(e["type_value"]) < 2:
            return None
    raw = e["type_value"][1] & 0xFF
    return raw - 256 if raw > 127 else raw


_BAT_LEVEL_TO_PCT = {0: 100, 1: 75, 2: 50, 3: 25, 4: 10}


def _dec_bat(entries, dp_index):
    e = _find_entry(entries, dp_index, "STA_BAT", "BAT")
    if e is None or len(e["type_value"]) < 2:
        return None
    raw = e["type_value"][1] & 0xFF
    return _BAT_LEVEL_TO_PCT.get(raw, None)


def _dec_alarm(entries, dp_index, port=None):
    e = _find_by_identity(entries, dp_index, "STA_ALARM", port)
    if e is None:
        e = _find_by_name(entries, "ALARM")
    if e is None:
        return None
    return e["type_value"][0] & 0x0F


def _dec_temperature(entries, dp_index, temp_unit):
    e = _find_entry(entries, dp_index, "STA_TEM", "TEM")
    if e is None or e["type_len"] < 2 or len(e["type_value"]) < 3:
        return None
    payload = e["type_value"][1:3]
    buf = bytes(payload + [0] * 6)
    raw = struct.unpack_from("<q", buf)[0]
    if raw > 32767:
        raw -= 65536
    if raw == 32767:
        return "HH"
    if raw == -32768:
        return "LL"
    if raw == 50000:
        return None
    return _temp_from_raw(raw, temp_unit)


def _dec_humidity(entries, dp_index):
    e = _find_entry(entries, dp_index, "STA_RH", "RH")
    if e is None or len(e["type_value"]) < 2:
        return None
    v = e["type_value"][1] & 0xFF
    return None if v == 255 else v


def _dec_illuminance(entries, dp_index):
    e = _find_entry(entries, dp_index, "STA_ILLUMINANCE", "ILLUMINANCE")
    if e is None or e["type_len"] <= 0:
        return None
    raw = _le_int(e)
    return None if raw == 16777215 else raw // 10


def _dec_co2(entries, dp_index):
    e = _find_entry(entries, dp_index, "STA_CO2", "CO2")
    if e is None or len(e["type_value"]) < 3:
        return None
    payload = e["type_value"][1:3]
    buf = bytes(payload + [0] * 6)
    val = struct.unpack_from("<q", buf)[0] & 0xFFFF
    return None if val == 0xFFFF else int(val)


def _dec_co2_warning(entries, dp_index):
    e = _find_entry(entries, dp_index, "STA_CO2", "CO2")
    if e is None or len(e["type_value"]) < 5:
        return None
    payload = e["type_value"][3:5]
    buf = bytes(payload + [0] * 6)
    val = struct.unpack_from("<q", buf)[0] & 0xFFFF
    return None if val == 0xFFFF else int(val)


def _dec_work_mode(entries, dp_index, port=None):
    e = _find_by_identity(entries, dp_index, "STA_WKSTATE", port)
    if e is None:
        e = _find_by_name(entries, "WK_STATE")
    if e is None or len(e["type_value"]) < 2:
        return None
    raw = e["type_value"][1] & 0x0F
    return {"raw": raw, "label": _WORK_MODES.get(raw, f"unknown_{raw}")}


def _dec_duration(entries, dp_index, port=None):
    e = _find_by_identity(entries, dp_index, "STA_DURATION", port)
    if e is None:
        e = _find_by_name(entries, "DURATION")
    if e is None or e["type_len"] <= 0:
        return None
    return int(_le_int(e))


def _dec_last_usage(entries, dp_index, unit, port=None):
    e = _find_by_identity(entries, dp_index, "STA_LASTUSAGE", port)
    if e is None:
        e = _find_by_name(entries, "LAST_USAGE")
    if e is None or e["type_len"] <= 0:
        return None
    return _vol(_le_int(e), unit)


def _dec_total_usage(entries, dp_index, unit):
    e = _find_entry(entries, dp_index, "STA_TOTAL", "WATER_TOTAL")
    if e is None or e["type_len"] <= 0:
        return None
    raw = _le_int(e)
    if raw == 0xFFFFFFFF:
        return None
    return round(raw / 10.0, 2) if unit == "L" else float(
        Decimal(str((raw / 10.0) * 0.2642)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _dec_flow_rate(entries, dp_index, unit):
    e = _find_entry(entries, dp_index, "STA_FLOW", "V_FLOW")
    if e is None or e["type_len"] <= 0:
        return None
    raw = _le_int(e)
    if unit == "L":
        return round(raw / 10.0, 2)
    return float(Decimal(str((raw / 10.0) * 0.2642)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _dec_event_time(entries, dp_index, port=None):
    e = _find_by_identity(entries, dp_index, "STA_EVTIME", port)
    if e is None:
        e = _find_by_name(entries, "EVENT_TIME")
    if e is None or len(e["type_value"]) < 5:
        return None
    payload = e["type_value"][1:5]
    return struct.unpack_from("<I", bytes(payload + [0] * 4))[0]


def _dec_event_time2(entries, dp_index, port=None):
    e = _find_by_identity(entries, dp_index, "STA_EVTIME2", port)
    if e is None or len(e["type_value"]) < 5:
        return None
    payload = e["type_value"][1:5]
    return struct.unpack_from("<I", bytes(payload + [0] * 4))[0]


def _dec_total_rain(entries, dp_index):
    e = _find_entry(entries, dp_index, "STA_TOTAL_RAIN", "TOTAL_RAIN")
    if e is None or e["type_len"] <= 0:
        return None
    return round(_le_int(e) / 10.0, 1)


def _dec_hour_rain(entries, dp_index):
    e = _find_entry(entries, dp_index, "STA_HOUR_RAIN", "HOUR_RAIN")
    if e is None or e["type_len"] <= 0:
        return None
    return round(_le_int(e) / 10.0, 1)


def _dec_day_rain(entries, dp_index):
    e = _find_entry(entries, dp_index, "STA_DAY_RAIN", "DAY_RAIN")
    if e is None or e["type_len"] <= 0:
        return None
    return round(_le_int(e) / 10.0, 1)


def _dec_today_water(entries, dp_index, unit):
    e = _find_entry(entries, dp_index, "STA_TOTAL_TODAY", "TOTAL_TODAY")
    if e is None or e["type_len"] <= 0:
        return None
    raw = _le_int(e)
    if raw == 0xFFFFFFFF:
        return None
    return _vol(raw, unit)


def _dec_air_pressure(entries, dp_index):
    e = _find_entry(entries, dp_index, "STA_ATMOS", "ATMOS")
    if e is None or e["type_len"] <= 0:
        return None
    raw = _le_int(e)
    return None if raw == 0xFFFFFFFF else round(raw / 10.0, 1)


# ---------------------------------------------------------------------------
# Per-port decoder
# ---------------------------------------------------------------------------

def _decode_port(entries: list[dict], dp_index: dict[int, dict],
                 port: int | None, unit: str, temp_unit: str,
                 model_str: str = "") -> dict:
    result: dict = {}

    wm = _dec_work_mode(entries, dp_index, port)
    if wm is not None:
        result["valve_state"] = wm["label"]
        result["is_watering"] = wm["raw"] > 0

    dur = _dec_duration(entries, dp_index, port)
    if dur is not None:
        result["current_session_duration"] = dur

    lu = _dec_last_usage(entries, dp_index, unit, port)
    if lu is not None:
        result["last_water_volume"] = lu

    et = _dec_event_time(entries, dp_index, port)
    if et is not None and et > 1_000_000_000:
        result["event_time"] = datetime.fromtimestamp(et, tz=timezone.utc).isoformat()

    et2 = _dec_event_time2(entries, dp_index, port)
    if et2 is not None and et2 > 1_000_000_000:
        result["event_time2"] = datetime.fromtimestamp(et2, tz=timezone.utc).isoformat()

    alarm = _dec_alarm(entries, dp_index, port)
    if alarm is not None:
        result["alarm"] = alarm

    t = _dec_temperature(entries, dp_index, temp_unit)
    if t is not None:
        result["temperature"] = t

    h = _dec_humidity(entries, dp_index)
    if h is not None:
        if model_str.upper() in SOIL_MOISTURE_MODELS:
            result["soil_moisture"] = h
        else:
            result["humidity"] = h

    il = _dec_illuminance(entries, dp_index)
    if il is not None:
        result["illuminance"] = il

    co2 = _dec_co2(entries, dp_index)
    if co2 is not None:
        result["carbon_dioxide"] = co2

    co2_warn = _dec_co2_warning(entries, dp_index)
    if co2_warn is not None:
        result["carbon_dioxide_warning_threshold"] = co2_warn

    tu = _dec_total_usage(entries, dp_index, unit)
    if tu is not None:
        result["total_water_volume"] = tu

    fr = _dec_flow_rate(entries, dp_index, unit)
    if fr is not None:
        result["flow_rate"] = fr
        result["flow_rate_unit"] = f"{unit}/min"

    tr = _dec_total_rain(entries, dp_index)
    if tr is not None:
        result["precipitation_total"] = tr

    hr = _dec_hour_rain(entries, dp_index)
    if hr is not None:
        result["precipitation_1h"] = hr

    dr = _dec_day_rain(entries, dp_index)
    if dr is not None:
        result["precipitation_24h"] = dr

    tw = _dec_today_water(entries, dp_index, unit)
    if tw is not None:
        result["today_water_volume"] = tw

    ap = _dec_air_pressure(entries, dp_index)
    if ap is not None:
        result["air_pressure"] = ap

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decode_payload(model: str, status_param: str,
                   unit: str = "L", temp_unit: str = "C") -> dict:
    """
    Decode a statusParam payload for a given device model.

    Returns a dict of sensor fields. For single-port devices the fields are
    at the top level. For multi-port devices, per-port fields are nested under
    'port_1', 'port_2', ... with shared fields (battery, signal) at the top.

    On unknown model or decode error, returns a dict with an 'error' key.
    """
    unit = unit.upper()
    temp_unit = temp_unit.upper()
    models = _load_models()

    model_dict: dict | None = None
    for k, v in models.items():
        if k.upper() == model.upper():
            model_dict = v
            break

    if model_dict is None:
        _LOGGER.warning("decode_payload: model '%s' not found in product_models.json", model)
        return {"error": f"Model '{model}' not found in product_models.json"}

    dp_index = _build_dp_index(model_dict)
    port_number = model_dict.get("portNumber", 1) or 1  # treat 0 as 1
    dp_flag = model_dict.get("dpFlag", 1)

    try:
        if _is_legacy(status_param):
            leg = _parse_legacy(status_param)
            sensor_data = _decode_legacy_fields(leg, unit, temp_unit, port_number)
            if model.upper() in SOIL_MOISTURE_MODELS and "humidity" in sensor_data:
                sensor_data["soil_moisture"] = sensor_data.pop("humidity")
        else:
            hex_data, z8 = _parse_prefix(status_param)
            raw_bytes = _hex_to_bytes(hex_data)
            entries = _parse_tlv(raw_bytes, z8)

            shared = {k: v for k, v in {
                "battery_level": _dec_bat(entries, dp_index),
                "signal_strength": _dec_rssi(entries, dp_index),
            }.items() if v is not None}

            is_bitmask_hub = (port_number > 1 and not z8 and any(
                dp.get("identity") == "STA_WATER_ZONES"
                for dp in model_dict.get("dp", [])
            ))
            if port_number <= 1 or (not z8 and not is_bitmask_hub):
                port_data = _decode_port(entries, dp_index, None, unit, temp_unit, model)
                sensor_data = {**shared, **port_data}
            elif is_bitmask_hub:
                sensor_data = dict(shared)
            else:
                sensor_data = dict(shared)
                for p in range(1, port_number + 1):
                    port_entries = _entries_for_port(entries, dp_index, p)
                    port_data = _decode_port(port_entries, dp_index, p, unit, temp_unit, model)
                    if port_data:
                        sensor_data[f"port_{p}"] = port_data

            # Bitmask hub (e.g. HIC801W): STA_WATER_ZONES byte encodes zone states.
            # These devices have z8=False so the per-port branch above is skipped;
            # handle them here regardless of z8.
            if port_number > 1:
                wz_dpcode = next((
                    dp["dpCode"] for dp in model_dict.get("dp", [])
                    if dp.get("identity") == "STA_WATER_ZONES"
                ), None)
                wz_entries = []
                if wz_dpcode is not None:
                    wz_entries = [e for e in entries if e["type_code"] == wz_dpcode]
                if wz_entries:
                    # TLV type_value[0] is the header byte; the actual 4-byte
                    # WATER_ZONES payload starts at index 1.
                    zone_byte = wz_entries[0]["type_value"][1] & 0xFF if len(wz_entries[0]["type_value"]) > 1 else 0
                    # HIC801W reports the active zone as an ordinal in the
                    # first payload byte: 0=all off, 1..8=that exact zone on.
                    if model == "HIC801W":
                        bitmask = 0 if zone_byte == 0 else (1 << (zone_byte - 1)) if 1 <= zone_byte <= port_number else 0
                    else:
                        bitmask = zone_byte
                    for p in range(1, port_number + 1):
                        port_key = f"port_{p}"
                        active = bool(bitmask & (1 << (p - 1)))
                        if port_key not in sensor_data:
                            sensor_data[port_key] = {}
                        if "is_watering" not in sensor_data[port_key]:
                            sensor_data[port_key]["is_watering"] = active
                        if "valve_state" not in sensor_data[port_key]:
                            sensor_data[port_key]["valve_state"] = "irrigation" if active else "idle"

    except Exception as exc:
        _LOGGER.exception("decode_payload error for model=%s: %s", model, exc)
        return {"error": str(exc)}

    result = {
        "port_number": port_number,
        "dp_flag": dp_flag,
        **sensor_data,
    }
    return result
