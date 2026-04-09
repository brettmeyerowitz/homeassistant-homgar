"""Test EU ASCII format decoders for HCS014ARF, HCS012ARF, and HWS388WRF-V13.

These tests use the exact raw payloads reported in GitHub issue #29.
"""
import sys
sys.path.insert(0, '/config')
sys.path.insert(0, '/usr/src/homeassistant')

PASS = 0
FAIL = 0


def check(label, got, expected, tol=0.15):
    global PASS, FAIL
    if got is None and expected is None:
        PASS += 1
        return
    if got is None or expected is None:
        print(f"FAIL [{label}]: got={got} expected={expected}")
        FAIL += 1
        return
    if isinstance(expected, float) or isinstance(got, float):
        ok = abs(float(got) - float(expected)) <= tol
    else:
        ok = got == expected
    if ok:
        PASS += 1
    else:
        print(f"FAIL [{label}]: got={got!r} expected={expected!r}")
        FAIL += 1


# --- HWS019WRF-V2 / HWS388WRF-V13 Display Hub ---
from custom_components.homgar.api.decoders.hws019wrf_v2 import decode_hws019wrf_v2

# US format (existing)
r = decode_hws019wrf_v2('1,136;781(781/723/1),52(64/50/1),P=10213(10222/10205/1),')
check('DisplayHub US temp_current_c', r.get('temp_current_c'), round((781/10-32)*5/9, 1))
check('DisplayHub US humidity_current', r.get('humidity_current'), 52)
check('DisplayHub US pressure_current_hpa', r.get('pressure_current_hpa'), round(10213/100, 1))
check('DisplayHub US temp_high_c', r.get('temp_high_c'), round((781/10-32)*5/9, 1))
check('DisplayHub US temp_low_c', r.get('temp_low_c'), round((723/10-32)*5/9, 1))
check('DisplayHub US humidity_high', r.get('humidity_high'), 64)
check('DisplayHub US humidity_low', r.get('humidity_low'), 50)

# EU format (issue #29 payload)
r = decode_hws019wrf_v2('1,0,1;816(816/816/1),31(31/31/1),P=10294(10294/10294/1),')
check('DisplayHub EU temp_current_c', r.get('temp_current_c'), round((816/10-32)*5/9, 1))
check('DisplayHub EU humidity_current', r.get('humidity_current'), 31)
check('DisplayHub EU pressure_current_hpa', r.get('pressure_current_hpa'), round(10294/100, 1))


# --- HCS014ARF Temperature/Humidity ---
from custom_components.homgar.api.decoders.hcs014arf import decode_hcs014arf

# US binary format (regression)
US_HCS014 = '10#E1AF00FF0B0C09010000E11B00B70028190000E11C00B70028190000DC0064DC01640000'
r = decode_hcs014arf(US_HCS014)
check('HCS014ARF US type', r.get('type'), 'temphum')
check('HCS014ARF US decoder not error', 'error' in r.get('decoder', ''), False)

# EU ASCII format — Sensor 01#1: 26.6°C, 30%
r = decode_hcs014arf('1,0,1;798(798/798/1),30(30/30/1),')
check('HCS014ARF EU1 type', r.get('type'), 'temphum')
check('HCS014ARF EU1 tempcurrent', r.get('tempcurrent'), round((798/10-32)*5/9, 1))
check('HCS014ARF EU1 humiditycurrent', r.get('humiditycurrent'), 30)
check('HCS014ARF EU1 decoder', r.get('decoder'), 'hcs014arf_ascii')

# EU ASCII format — Sensor 02#2: 26.8°C, 30%
r = decode_hcs014arf('1,0,1;802(804/802/1),30(30/30/1),')
check('HCS014ARF EU2 tempcurrent', r.get('tempcurrent'), round((802/10-32)*5/9, 1))
check('HCS014ARF EU2 humiditycurrent', r.get('humiditycurrent'), 30)

# EU ASCII format — Sensor 03#3: 2.4°C, 86%
r = decode_hcs014arf('1,0,1;363(363/356/1),86(86/80/1),')
check('HCS014ARF EU3 tempcurrent', r.get('tempcurrent'), round((363/10-32)*5/9, 1))
check('HCS014ARF EU3 humiditycurrent', r.get('humiditycurrent'), 86)

# EU format without trailing comma
r = decode_hcs014arf('1,0,1;798(798/798/1),30(30/30/1)')
check('HCS014ARF EU no-comma tempcurrent', r.get('tempcurrent'), round((798/10-32)*5/9, 1))


# --- HCS012ARF Rain Gauge ---
from custom_components.homgar.api.decoders.hcs012arf import decode_hcs012arf

# EU ASCII format — 0.0 mm rain
r = decode_hcs012arf('1,0,1;0(0/0/1),0(0/0/1),0(0/0/1),0(0/0/1),')
check('HCS012ARF EU type', r.get('type'), 'rain')
check('HCS012ARF EU rain_last_hour_mm', r.get('rain_last_hour_mm'), 0.0)
check('HCS012ARF EU rain_last_24h_mm', r.get('rain_last_24h_mm'), 0.0)
check('HCS012ARF EU decoder', r.get('decoder'), 'hcs012arf_ascii')

# EU ASCII format — with actual rain values
r = decode_hcs012arf('1,0,1;25(25/0/1),47(47/0/1),85(85/0/1),120(120/0/1),')
check('HCS012ARF EU rain_last_hour_mm', r.get('rain_last_hour_mm'), 2.5)
check('HCS012ARF EU rain_last_24h_mm', r.get('rain_last_24h_mm'), 4.7)
check('HCS012ARF EU rain_last_7d_mm', r.get('rain_last_7d_mm'), 8.5)
check('HCS012ARF EU rain_total_mm', r.get('rain_total_mm'), 12.0)

# 3-field variant (no total)
r = decode_hcs012arf('1,0,1;25(25/0/1),47(47/0/1),85(85/0/1),')
check('HCS012ARF EU 3-field hour', r.get('rain_last_hour_mm'), 2.5)
check('HCS012ARF EU 3-field 24h', r.get('rain_last_24h_mm'), 4.7)
check('HCS012ARF EU 3-field 7d', r.get('rain_last_7d_mm'), 8.5)
check('HCS012ARF EU 3-field total', r.get('rain_total_mm'), 0.0)


# --- utils helpers ---
from custom_components.homgar.api.utils import _parse_stats, _parse_ascii_sensor_payload

val, hi, lo = _parse_stats('816(816/723/1)')
check('_parse_stats current', val, 816)
check('_parse_stats hi', hi, 816)
check('_parse_stats lo', lo, 723)

val, hi, lo = _parse_stats('52')
check('_parse_stats bare int', val, 52)
check('_parse_stats bare int hi', hi, None)

fields, batt, rssi = _parse_ascii_sensor_payload('1,0,1;798(798/798/1),30(30/30/1),')
check('_parse_ascii fields len', len(fields), 2)
check('_parse_ascii battery_code', batt, 1)
check('_parse_ascii rssi_dbm', rssi, 0)

fields, batt, rssi = _parse_ascii_sensor_payload('1,136;781(781/723/1),52(64/50/1),')
check('_parse_ascii 2-part fields len', len(fields), 2)
check('_parse_ascii 2-part rssi_dbm', rssi, -136)

# Binary payload must return None
fields, batt, rssi = _parse_ascii_sensor_payload('10#AABBCC')
check('_parse_ascii binary returns None', fields, None)

# Payload without semicolon must return None
fields, batt, rssi = _parse_ascii_sensor_payload('something_without_semicolon')
check('_parse_ascii no-semicolon returns None', fields, None)


print(f"\nEU_DECODER_TEST:{PASS}pass,{FAIL}fail")
if FAIL == 0:
    print('EU_DECODER_TEST:PASS')
else:
    sys.exit(1)
