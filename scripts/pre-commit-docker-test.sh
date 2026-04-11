#!/bin/bash

# Pre-commit Docker testing script for v3+
# Tests the v3 decoder architecture (product_models.json + decode_payload)

set -e

echo "🔍 Running pre-commit Docker testing..."

# ── Version consistency check ──────────────────────────────────────────────
echo "🔍 Checking manifest version..."
MANIFEST_VERSION=$(grep '"version"' custom_components/homgar/manifest.json | sed 's/.*"version": "\(.*\)".*/\1/')

if [ -z "$MANIFEST_VERSION" ]; then
    echo "❌ ERROR: Could not read version from manifest.json"
    exit 1
fi
echo "✅ Version: $MANIFEST_VERSION"

# ── Docker container check ─────────────────────────────────────────────────
if ! docker ps | grep -q "ha-test"; then
    echo "❌ ERROR: Docker container 'ha-test' is not running"
    echo "Please start it with: docker start ha-test"
    exit 1
fi
echo "✅ Docker container 'ha-test' is running"

# ── Deploy to Docker ───────────────────────────────────────────────────────
echo "📦 Copying integration to Docker container..."
# Remove files deleted from the repo that may still exist in Docker (+ clear pycache)
DELETED_FILES="debug.py device.py mqtt_diagnostics.py switch.py"
for f in $DELETED_FILES; do
    docker exec ha-test rm -f "/config/custom_components/homgar/$f" 2>/dev/null || true
done
docker exec ha-test find /config/custom_components/homgar/__pycache__ -name "*.pyc" -delete 2>/dev/null || true
docker cp custom_components/homgar ha-test:/config/custom_components/ > /dev/null 2>&1
echo "🔄 Restarting Docker container..."
docker restart ha-test > /dev/null 2>&1
echo "⏳ Waiting for HA to start..."
sleep 25

RECENT_LOGS=$(docker logs ha-test --since="30s" 2>&1)

# ── HA startup checks ──────────────────────────────────────────────────────
if echo "$RECENT_LOGS" | grep -q "Setup failed for custom integration 'homgar'"; then
    echo "❌ ERROR: Integration setup failed"
    echo "$RECENT_LOGS" | grep "Setup failed" -A 3 | tail -10
    exit 1
fi
if echo "$RECENT_LOGS" | grep -q "cannot import name"; then
    echo "❌ ERROR: Import error detected"
    echo "$RECENT_LOGS" | grep "cannot import name" -A 2 | tail -10
    exit 1
fi
if echo "$RECENT_LOGS" | grep -q "No module named"; then
    echo "❌ ERROR: Missing module detected"
    echo "$RECENT_LOGS" | grep "No module named" -A 2 | tail -10
    exit 1
fi
if echo "$RECENT_LOGS" | grep -q "Setup of domain homgar took"; then
    echo "✅ HomGar integration setup successfully"
else
    echo "❌ ERROR: Integration did not set up within 30s"
    echo "$RECENT_LOGS" | grep -i "homgar" | tail -5
    exit 1
fi

# ── Test: decoder module loads and has correct model count ─────────────────
echo "🧪 Testing decoder module loads..."
DECODER_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.insert(0, '/config/custom_components')
from custom_components.homgar.decoder import _MODELS, decode_payload
count = len(_MODELS)
if count >= 100:
    print(f'DECODER_TEST:PASS:{count}')
else:
    print(f'DECODER_TEST:FAIL:only {count} models loaded')
" 2>/dev/null)

if [[ $DECODER_TEST == DECODER_TEST:PASS* ]]; then
    echo "✅ Decoder loaded: $DECODER_TEST"
else
    echo "❌ ERROR: Decoder load failed"
    echo "Result: $DECODER_TEST"
    exit 1
fi

# ── Test: TLV decode (CO2 sensor — HCS0530THO) ────────────────────────────
echo "🧪 Testing TLV decode (HCS0530THO CO2 sensor)..."
CO2_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.insert(0, '/config/custom_components')
from custom_components.homgar.decoder import decode_payload
result = decode_payload('HCS0530THO', '10#CFCE01DC05DC01E78902AD02B80585A8028844E93F45FF0')
co2 = result.get('carbon_dioxide')
temp = result.get('temperature')
bat = result.get('battery_level')
if co2 and 300 <= co2 <= 5000 and temp and bat in (10,25,50,75,100):
    print(f'CO2_TEST:PASS:co2={co2},temp={temp},bat={bat}')
else:
    print(f'CO2_TEST:FAIL:{result}')
" 2>/dev/null)

if [[ $CO2_TEST == CO2_TEST:PASS* ]]; then
    echo "✅ CO2 decoder: $CO2_TEST"
else
    echo "❌ ERROR: CO2 decoder failed"
    echo "Result: $CO2_TEST"
    exit 1
fi

# ── Test: TLV decode (soil moisture — HCS021FRF) ──────────────────────────
echo "🧪 Testing TLV decode (HCS021FRF soil moisture)..."
SOIL_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.insert(0, '/config/custom_components')
from custom_components.homgar.decoder import decode_payload
result = decode_payload('HCS021FRF', '10#E1B300DC01859602881CC6C91800FF0F628B1619')
moisture = result.get('soil_moisture')
bat = result.get('battery_level')
rssi = result.get('signal_strength')
if moisture is not None and 0 <= moisture <= 100 and bat in (10,25,50,75,100) and rssi is not None:
    print(f'SOIL_TEST:PASS:moisture={moisture},bat={bat},rssi={rssi}')
else:
    print(f'SOIL_TEST:FAIL:{result}')
" 2>/dev/null)

if [[ $SOIL_TEST == SOIL_TEST:PASS* ]]; then
    echo "✅ Soil moisture decoder: $SOIL_TEST"
else
    echo "❌ ERROR: Soil moisture decoder failed"
    echo "Result: $SOIL_TEST"
    exit 1
fi

# ── Test: battery ordinal mapping ─────────────────────────────────────────
echo "🧪 Testing battery ordinal mapping..."
BAT_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.insert(0, '/config/custom_components')
from custom_components.homgar.decoder import _BAT_LEVEL_TO_PCT
expected = {0: 100, 1: 75, 2: 50, 3: 25, 4: 10}
if _BAT_LEVEL_TO_PCT == expected:
    print('BAT_TEST:PASS')
else:
    print(f'BAT_TEST:FAIL:{_BAT_LEVEL_TO_PCT}')
" 2>/dev/null)

if [[ $BAT_TEST == "BAT_TEST:PASS" ]]; then
    echo "✅ Battery ordinal mapping correct"
else
    echo "❌ ERROR: Battery mapping wrong"
    echo "Result: $BAT_TEST"
    exit 1
fi

# ── Test: legacy ASCII decode (HCS012ARF) ─────────────────────────────────
echo "🧪 Testing legacy ASCII decode (HCS012ARF)..."
LEGACY_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.insert(0, '/config/custom_components')
from custom_components.homgar.decoder import decode_payload
result = decode_payload('HCS012ARF', '1,84,0,0;R=4870(10/20/430/2340)')
if 'error' not in result:
    print(f'LEGACY_TEST:PASS:{list(result.keys())}')
else:
    print(f'LEGACY_TEST:FAIL:{result}')
" 2>/dev/null)

if [[ $LEGACY_TEST == LEGACY_TEST:PASS* ]]; then
    echo "✅ Legacy ASCII decoder: $LEGACY_TEST"
else
    echo "❌ ERROR: Legacy ASCII decoder failed"
    echo "Result: $LEGACY_TEST"
    exit 1
fi

# ── Test: multi-port valve decode (HTV213FRF) ─────────────────────────────
echo "🧪 Testing multi-port valve decode (HTV213FRF)..."
VALVE_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.insert(0, '/config/custom_components')
from custom_components.homgar.decoder import decode_payload
result = decode_payload('HTV213FRF', '11#17E1AE0019D8001AD8001D201E2021B70000000022B70000000018DC0125AD000026AD0000299F000000002A9F00000000FEFF0FF5151519')
has_ports = 'port_1' in result and 'port_2' in result
if has_ports:
    print(f'VALVE_TEST:PASS:ports={result[\"port_number\"]}')
else:
    print(f'VALVE_TEST:FAIL:{list(result.keys())}')
" 2>/dev/null)

if [[ $VALVE_TEST == VALVE_TEST:PASS* ]]; then
    echo "✅ Multi-port valve decoder: $VALVE_TEST"
else
    echo "❌ ERROR: Multi-port valve decoder failed"
    echo "Result: $VALVE_TEST"
    exit 1
fi

# ── Test: API client critical methods ─────────────────────────────────────
echo "🧪 Testing API client methods..."
API_TEST=$(docker exec ha-test python3 -c "
import sys, inspect
sys.path.insert(0, '/config/custom_components')
from custom_components.homgar.api.client import HomGarClient
required = ['ensure_logged_in', 'login', 'is_token_valid', 'list_homes',
            'get_devices_by_hid', 'subscribe_status']
missing = [m for m in required if not hasattr(HomGarClient, m)]
if missing:
    print(f'API_TEST:FAIL:Missing: {missing}')
elif not inspect.iscoroutinefunction(HomGarClient.ensure_logged_in):
    print('API_TEST:FAIL:ensure_logged_in not async')
else:
    print('API_TEST:PASS')
" 2>/dev/null)

if [[ $API_TEST == "API_TEST:PASS" ]]; then
    echo "✅ API client methods present"
else
    echo "❌ ERROR: API client check failed"
    echo "Result: $API_TEST"
    exit 1
fi

# ── Test: translation files valid ─────────────────────────────────────────
echo "🧪 Testing translation files..."
TRANSLATION_TEST=$(docker exec ha-test python3 -c "
import json
try:
    with open('/config/custom_components/homgar/translations/en.json') as f:
        t = json.load(f)
    if 'config' in t and 'step' in t['config'] and 'user' in t['config']['step']:
        print('TRANSLATION_TEST:PASS')
    else:
        print('TRANSLATION_TEST:FAIL:missing keys')
except Exception as e:
    print(f'TRANSLATION_TEST:FAIL:{e}')
" 2>/dev/null)

if [[ $TRANSLATION_TEST == "TRANSLATION_TEST:PASS" ]]; then
    echo "✅ Translation files valid"
else
    echo "❌ ERROR: Translation files invalid"
    echo "Result: $TRANSLATION_TEST"
    exit 1
fi

# ── Test: valve detection (get_valve_ports) ───────────────────────────────
echo "🧪 Testing dynamic valve detection..."
VALVE_DETECT_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.insert(0, '/config/custom_components')
from custom_components.homgar.decoder import get_valve_ports
ports_213 = get_valve_ports('HTV213FRF')
ports_soil = get_valve_ports('HCS021FRF')
if len(ports_213) >= 2 and len(ports_soil) == 0:
    print(f'VALVE_DETECT_TEST:PASS:HTV213FRF={ports_213},HCS021FRF={ports_soil}')
else:
    print(f'VALVE_DETECT_TEST:FAIL:HTV213FRF={ports_213},HCS021FRF={ports_soil}')
" 2>/dev/null)

if [[ $VALVE_DETECT_TEST == VALVE_DETECT_TEST:PASS* ]]; then
    echo "✅ Valve detection: $VALVE_DETECT_TEST"
else
    echo "❌ ERROR: Valve detection failed"
    echo "Result: $VALVE_DETECT_TEST"
    exit 1
fi

echo ""
echo "🎉 All pre-commit tests passed! Commit allowed."
exit 0
