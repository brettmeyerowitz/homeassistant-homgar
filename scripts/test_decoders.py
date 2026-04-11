"""
Decoder regression tests — run inside the ha-test Docker container.

Covers real payloads collected from GitHub issues and live device captures.
Each test asserts exact decoded field values or range/type constraints.
"""
import sys
sys.path.insert(0, "/config")

from custom_components.homgar.decoder import (
    decode_payload,
    get_valve_ports,
    _BAT_LEVEL_TO_PCT,
    _MODELS,
)

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  ✅ {name}")
        PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}")
        FAIL += 1


# ── Model registry ─────────────────────────────────────────────────────────
print("\n🧪 Model registry")
check("≥100 models loaded", len(_MODELS) >= 100, f"got {len(_MODELS)}")


# ── Battery ordinal mapping ─────────────────────────────────────────────────
print("\n🧪 Battery ordinal mapping")
expected_bat = {0: 100, 1: 75, 2: 50, 3: 25, 4: 10}
check("ordinal map correct", _BAT_LEVEL_TO_PCT == expected_bat, str(_BAT_LEVEL_TO_PCT))


# ── Valve detection ─────────────────────────────────────────────────────────
print("\n🧪 Valve port detection")
check("HTV213FRF has 2 ports", get_valve_ports("HTV213FRF") == [1, 2])
check("HTV0537FRF has 2 ports", get_valve_ports("HTV0537FRF") == [1, 2])
check("HIC801W has 8 ports",   len(get_valve_ports("HIC801W")) == 8)
check("HTV113FRF has 1 port",  get_valve_ports("HTV113FRF") == [1])
check("HTP115FRF has 1 port",  get_valve_ports("HTP115FRF") == [1])
check("HCS021FRF has 0 ports", get_valve_ports("HCS021FRF") == [])
check("HCS0530THO has 0 ports",get_valve_ports("HCS0530THO") == [])
check("HCS014ARF has 0 ports", get_valve_ports("HCS014ARF") == [])
check("HCS008FRF has 0 ports (no CTL_WATER dp — not a valve entity)", get_valve_ports("HCS008FRF") == [])


# ── HCS0530THO — CO2/temp/humidity sensor (issue #21 related model) ─────────
print("\n🧪 HCS0530THO — CO2 / temp / humidity (TLV)")
# Use a payload that contains RSSI (not all payloads include it)
r = decode_payload("HCS0530THO", "10#CFCB01DC05DC01E789028103B80585D802883FE92744FF08A7013C02FF0F944B1719")
check("no error",          "error" not in r)
check("CO2 in range",      r.get("carbon_dioxide") is not None and 300 <= r["carbon_dioxide"] <= 5000,
      str(r.get("carbon_dioxide")))
check("temp in range",     r.get("temperature") is not None and -10 <= r["temperature"] <= 50,
      str(r.get("temperature")))
check("battery valid",     r.get("battery_level") in (10, 25, 50, 75, 100),
      str(r.get("battery_level")))
# Note: HCS0530THO does not include an RSSI TLV entry in its payload
check("CO2_warning present", r.get("carbon_dioxide_warning_threshold") is not None)

# Second real payload with different CO2/temp values
r2 = decode_payload("HCS0530THO", "10#CFCE01DC05DC01E78902AD02B80585A8028844E93F45FF0")
check("payload2 CO2 in range", r2.get("carbon_dioxide") is not None and 300 <= r2["carbon_dioxide"] <= 5000)
check("payload2 temp in range", r2.get("temperature") is not None and -10 <= r2["temperature"] <= 50)
check("payload2 battery valid", r2.get("battery_level") in (10, 25, 50, 75, 100))


# ── HCS014ARF — temperature/humidity sensor (issue #21) ─────────────────────
print("\n🧪 HCS014ARF — temperature/humidity (issue #21)")
# ASCII EU format: battery,rssi,bat_code;temp_raw(hi/lo/count),rh(hi/lo/count)
# temp_c = (raw/10 - 32) * 5/9
# payload: 798 raw -> (79.8-32)*5/9 = 26.6°C, 30% rh
r = decode_payload("HCS014ARF", "1,0,1;798(798/798/1),30(30/30/1),")
check("no error",       "error" not in r, str(r))
check("temp≈26.6°C",    r.get("temperature") is not None and 26.0 <= r["temperature"] <= 27.2,
      str(r.get("temperature")))
check("humidity=30%",   r.get("humidity") == 30, str(r.get("humidity")))

# payload: 363 raw -> (36.3-32)*5/9 = 2.4°C, 86% rh
r2 = decode_payload("HCS014ARF", "1,0,1;363(363/356/1),86(86/80/1),")
check("payload2 temp≈2.4°C", r2.get("temperature") is not None and 1.8 <= r2["temperature"] <= 3.0,
      str(r2.get("temperature")))
check("payload2 humidity=86%", r2.get("humidity") == 86, str(r2.get("humidity")))

# payload: 802 raw -> (80.2-32)*5/9 = 26.8°C
r3 = decode_payload("HCS014ARF", "1,0,1;802(804/802/1),30(30/30/1),")
check("payload3 temp≈26.8°C", r3.get("temperature") is not None and 26.2 <= r3["temperature"] <= 27.4,
      str(r3.get("temperature")))

# Temperature conversion regression: (raw/10 - 32) * 5/9, NOT raw/10 - 32
# If bug recurs, 798 raw would decode as ~47.8°C instead of ~26.6°C
check("F→C uses ×5/9 factor (not just -32)",
      r.get("temperature") is not None and r["temperature"] < 35,
      f"got {r.get('temperature')}°C — if >35 the ×5/9 factor is missing")


# ── HCS021FRF — soil moisture (single-port) ──────────────────────────────────
print("\n🧪 HCS021FRF — soil moisture (TLV)")
r = decode_payload("HCS021FRF", "10#E1B300DC01859602881CC6C91800FF0F628B1619")
check("no error",         "error" not in r)
check("soil_moisture",    r.get("soil_moisture") is not None and 0 <= r["soil_moisture"] <= 100,
      str(r.get("soil_moisture")))
check("battery valid",    r.get("battery_level") in (10, 25, 50, 75, 100))
check("signal_strength",  r.get("signal_strength") is not None and r["signal_strength"] < 0)


# ── HCS008FRF — flow meter (issue session) ───────────────────────────────────
print("\n🧪 HCS008FRF — flow meter (TLV)")
r = decode_payload("HCS008FRF", "10#E1AF00FF0B1A810100DC01990000B7EB4C1719FF0700000000AF000000009F05000000FF0A06000000CB371A0000B3519B0100FF0FEB4C1719")
check("no error",              "error" not in r)
check("battery_level=75",      r.get("battery_level") == 75, str(r.get("battery_level")))
check("signal_strength=-81",   r.get("signal_strength") == -81, str(r.get("signal_strength")))
check("total_water_volume",    r.get("total_water_volume") is not None and r["total_water_volume"] > 0,
      str(r.get("total_water_volume")))
check("today_water_volume",    r.get("today_water_volume") is not None,
      str(r.get("today_water_volume")))
check("flow_rate≥0",           r.get("flow_rate") is not None and r["flow_rate"] >= 0)


# ── HTV113FRF — single-port valve (v3.0.10 fix: is_watering at top level) ───
print("\n🧪 HTV113FRF — single-port valve (top-level is_watering)")
# Idle payload
r = decode_payload("HTV113FRF", "10#E1AD00DC01D80020B700000000AD00009F00000000FF0F4D371719")
check("no error",         "error" not in r)
check("is_watering=False",r.get("is_watering") is False, str(r.get("is_watering")))
check("valve_state=idle", r.get("valve_state") == "idle", str(r.get("valve_state")))
check("NOT nested in port_1", "port_1" not in r)

# Watering payload (current_session_duration > 0)
r2 = decode_payload("HTV113FRF", "10#E1AE00DC01D82020B700000000AD58029F00000000FF0F47371719")
check("payload2 no error",     "error" not in r2)
check("payload2 is_watering",  r2.get("is_watering") is True or r2.get("current_session_duration", 0) > 0,
      str(r2))


# ── HTV213FRF — multi-port valve, TLV (issue #17, #24) ──────────────────────
print("\n🧪 HTV213FRF — 2-zone valve (TLV)")
r = decode_payload("HTV213FRF", "11#17E1AE0019D8001AD8001D201E2021B70000000022B70000000018DC0125AD000026AD0000299F000000002A9F00000000FEFF0FF5151519")
check("no error",        "error" not in r)
check("port_1 present",  "port_1" in r)
check("port_2 present",  "port_2" in r)
check("port_number=2",   r.get("port_number") == 2)
check("port_1 idle",     r["port_1"].get("valve_state") == "idle")
check("port_2 idle",     r["port_2"].get("valve_state") == "idle")

# ASCII format — zone 2 open (from issue #17 log)
r2 = decode_payload("HTV213FRF", "1,-75,1;0,3,0,0,0,0|33,15,0,1775856207,600,0")
check("ASCII no error",       "error" not in r2, str(r2))
check("ASCII port_1 idle",    r2.get("port_1", {}).get("is_watering") is False,
      str(r2.get("port_1")))
check("ASCII port_2 watering",r2.get("port_2", {}).get("is_watering") is True,
      str(r2.get("port_2")))

# ASCII — zone 2 closed
r3 = decode_payload("HTV213FRF", "1,-74,1;0,3,0,0,0,0|0,14,0,0,0,0")
check("ASCII closed port_2",  r3.get("port_2", {}).get("is_watering") is False,
      str(r3.get("port_2")))


# ── HTV245FRF — 2-zone valve (issue #17) ────────────────────────────────────
print("\n🧪 HTV245FRF — 2-zone valve")
r = decode_payload("HTV245FRF", "11#17E1AE0019D8001AD8001D201E2021B70000000022B70000000018DC0125AD000026AD0000299F000000002A9F00000000FEFF0FF5151519")
check("no error",       "error" not in r)
check("has port_1",     "port_1" in r)
check("has port_2",     "port_2" in r)


# ── HTV0537FRF — 2-zone valve (issue #26) ───────────────────────────────────
print("\n🧪 HTV0537FRF — 2-zone valve (issue #26)")
r = decode_payload("HTV0537FRF", "11#17E1AE0019D8001AD8001D201E2021B70000000022B70000000018DC0125AD000026AD0000299F000000002A9F00000000FEFF0FF5151519")
check("no error",        "error" not in r)
check("port_1 present",  "port_1" in r)
check("port_2 present",  "port_2" in r)
check("battery present", r.get("battery_level") is not None)
check("signal present",  r.get("signal_strength") is not None)


# ── HIC801W — 8-zone WiFi hub (issue #20) ───────────────────────────────────
print("\n🧪 HIC801W — 8-zone WiFi hub (issue #20)")
r = decode_payload("HIC801W", "10#108800AF00000000B700204200D800F700000000F9FF00")
check("no error",        "error" not in r)
check("8 ports detected",get_valve_ports("HIC801W") == list(range(1, 9)))
# All zones off — bitmask 0x00
check("zones dict present", "zones" in r or any(f"port_{i}" in r for i in range(1, 9)),
      str(list(r.keys())))


# ── HTP115FRF — pump/valve (issue #31) ──────────────────────────────────────
print("\n🧪 HTP115FRF — pump valve (issue #31)")
r = decode_payload("HTP115FRF", "10#00E1A300DC01D800B700000000AD00009F3600000020FF0F542E1119")
check("no error",              "error" not in r)
check("battery_level=75",      r.get("battery_level") == 75,     str(r.get("battery_level")))
check("signal_strength=-93",   r.get("signal_strength") == -93,  str(r.get("signal_strength")))
check("valve_state present",   r.get("valve_state") is not None, str(r.get("valve_state")))
check("is_watering=False",     r.get("is_watering") is False,    str(r.get("is_watering")))
check("last_water_volume≈5.4L",
      r.get("last_water_volume") is not None and 5.0 <= r["last_water_volume"] <= 6.0,
      str(r.get("last_water_volume")))


# ── HCS012ARF — legacy ASCII rain gauge ──────────────────────────────────────
print("\n🧪 HCS012ARF — legacy ASCII rain gauge")
r = decode_payload("HCS012ARF", "1,84,0,0;R=4870(10/20/430/2340)")
check("no error",          "error" not in r)
check("has rain fields",   any(k in r for k in ("precipitation_total", "precipitation_1h", "precipitation_24h")))
check("battery present",   r.get("battery_level") is not None)
check("signal present",    r.get("signal_strength") is not None)


# ── Temperature conversion regression (issue #21 root cause) ─────────────────
print("\n🧪 Temperature conversion regression (F→C must use ×5/9)")
# HCS0530THO uses STA_TEM identity — same conversion path affected in issue #21
# If bug recurs (missing ×5/9), temp would read ~12°C too high
r_reg = decode_payload("HCS0530THO", "10#CFCB01DC05DC01E789028103B80585D802883FE92744FF08A7013C02FF0F944B1719")
temp_reg = r_reg.get("temperature")
check("HCS0530THO temp <35°C (would be ~35+ if ×5/9 missing)",
      temp_reg is not None and temp_reg < 35,
      f"got {temp_reg}°C")


# ── Summary ─────────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*50}")
print(f"Results: {PASS}/{total} passed, {FAIL} failed")
if FAIL > 0:
    print("❌ TESTS FAILED")
    sys.exit(1)
else:
    print("✅ ALL TESTS PASSED")
    sys.exit(0)
