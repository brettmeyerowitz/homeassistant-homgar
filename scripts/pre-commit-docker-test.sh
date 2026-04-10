#!/bin/bash

# Pre-commit Docker testing script
# This script runs Docker testing before allowing commits

set -e

echo "🔍 Running pre-commit Docker testing..."

# Check README version matches manifest version
echo "🔍 Checking README version..."
MANIFEST_VERSION=$(grep '"version"' custom_components/homgar/manifest.json | sed 's/.*"version": "\(.*\)".*/\1/')
README_VERSION=$(grep '"version":' README.md | head -1 | sed 's/.*"version": "\(.*\)".*/\1/')

if [ "$MANIFEST_VERSION" != "$README_VERSION" ]; then
    echo "❌ ERROR: README version doesn't match manifest version"
    echo "Manifest version: $MANIFEST_VERSION"
    echo "README version: $README_VERSION"
    echo "Please update the version in README.md (line ~262)"
    exit 1
fi

echo "✅ README version matches manifest version: $MANIFEST_VERSION"

# Check if Docker container is running
if ! docker ps | grep -q "ha-test"; then
    echo "❌ ERROR: Docker container 'ha-test' is not running"
    echo "Please start the Docker container with: docker start ha-test"
    exit 1
fi

echo "✅ Docker container 'ha-test' is running"

# Copy integration to Docker container
echo "📦 Copying integration to Docker container..."
docker cp custom_components/homgar ha-test:/config/custom_components/ > /dev/null 2>&1

# Copy updated files
docker cp custom_components/homgar/const.py ha-test:/config/custom_components/homgar/const.py > /dev/null 2>&1
docker cp custom_components/homgar/manifest.json ha-test:/config/custom_components/homgar/manifest.json > /dev/null 2>&1

# Restart Docker container
echo "🔄 Restarting Docker container..."
docker restart ha-test > /dev/null 2>&1

# Wait for container to be ready
echo "⏳ Waiting for container to be ready..."
sleep 10

# Check for import errors
echo "🔍 Checking for import errors..."
sleep 5  # Wait for container to fully start

# Get the most recent logs after restart
RECENT_LOGS=$(docker logs ha-test --since="60s" 2>&1)

# Check for setup failures in recent logs
if echo "$RECENT_LOGS" | grep -q "Setup failed for custom integration 'homgar'"; then
    echo "❌ ERROR: Integration setup failed in Docker"
    echo "Recent error details:"
    echo "$RECENT_LOGS" | grep "Setup failed for custom integration 'homgar'" -A 3 | tail -10
    exit 1
fi

# Check for import errors in recent logs
if echo "$RECENT_LOGS" | grep -q "cannot import name"; then
    echo "❌ ERROR: Import error in Docker"
    echo "Recent error details:"
    echo "$RECENT_LOGS" | grep "cannot import name" -A 2 | tail -10
    exit 1
fi

# Check for missing module errors in recent logs
if echo "$RECENT_LOGS" | grep -q "No module named"; then
    echo "❌ ERROR: Missing dependencies in Docker"
    echo "Recent error details:"
    echo "$RECENT_LOGS" | grep "No module named" -A 2 | tail -10
    exit 1
fi

# Verify version is loaded
echo "🔍 Verifying version is loaded..."
VERSION=$(grep "VERSION = " custom_components/homgar/const.py | cut -d'"' -f2)

# Test if the integration is working by testing imports
if echo "$RECENT_LOGS" | grep -q "Setup of domain homgar took"; then
    echo "✅ HomGar integration setup successfully"
    VERSION_LOADED=true
else
    echo "❌ HomGar integration setup failed"
    VERSION_LOADED=false
fi

# Check version in logs (may not appear if no devices are active)
if echo "$RECENT_LOGS" | grep -q "HomGar v$VERSION"; then
    echo "✅ Version $VERSION loaded successfully"
elif [ "$VERSION_LOADED" = true ]; then
    echo "✅ Integration loaded (version $VERSION confirmed in files)"
else
    echo "❌ ERROR: Version $VERSION not found in Docker logs"
    echo "Expected: HomGar v$VERSION"
    echo "Found in recent logs:"
    echo "$RECENT_LOGS" | grep "HomGar v" | tail -3
    exit 1
fi

# Test ASCII format decoding
echo "🧪 Testing ASCII format decoding..."
ASCII_TEST_RESULT=$(docker exec ha-test python3 -c "
import sys
sys.path.append('/config/custom_components')
from custom_components.homgar.homgar_api import decode_htv213frf
result = decode_htv213frf('1,-84,1;0,149,0,0,0,0|0,6,0,0,0,0')
print(f'ASCII_TEST:{result[\"decoder\"]}:{len(result[\"zones\"])}')" 2>/dev/null)

if [[ $ASCII_TEST_RESULT == "ASCII_TEST:htv213frf_ascii:2" ]]; then
    echo "✅ ASCII format decoding test passed"
else
    echo "❌ ERROR: ASCII format decoding test failed"
    echo "Expected: ASCII_TEST:htv213frf_ascii:2"
    echo "Got: $ASCII_TEST_RESULT"
    exit 1
fi

# Test sensor ASCII format decoding
echo "🧪 Testing sensor ASCII format decoding..."
SENSOR_TEST_RESULT=$(docker exec ha-test python3 -c "
import sys
sys.path.append('/config/custom_components')
from custom_components.homgar.homgar_api import decode_hcs021frf
result = decode_hcs021frf('1,-73,1;694,70,G=292478')
# Test temperature is in expected range (20.77-20.78°C for 69.4°F)
temp = result['temperature_c']
if 20.77 <= temp <= 20.79:
    print('SENSOR_TEST:hcs021frf_ascii:PASS')
else:
    print(f'SENSOR_TEST:hcs021frf_ascii:FAIL:{temp}')" 2>/dev/null)

if [[ $SENSOR_TEST_RESULT == "SENSOR_TEST:hcs021frf_ascii:PASS" ]]; then
    echo "✅ Sensor ASCII format decoding test passed"
else
    echo "❌ ERROR: Sensor ASCII format decoding test failed"
    echo "Expected: Temperature in range 20.77-20.79°C (69.4°F converted)"
    echo "Got: $SENSOR_TEST_RESULT"
    exit 1
fi

# Test API client critical methods
echo "🧪 Testing API client critical methods..."
API_CLIENT_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.append('/config/custom_components')
from custom_components.homgar.api.client import HomGarClient
import inspect

# Check for critical methods that must exist
required_methods = ['ensure_logged_in', 'login', 'is_token_valid', 'list_homes', 'get_devices_by_hid']
missing_methods = []

for method in required_methods:
    if not hasattr(HomGarClient, method):
        missing_methods.append(method)

if missing_methods:
    print(f'API_CLIENT_TEST:FAIL:Missing methods: {missing_methods}')
else:
    # Verify ensure_logged_in is async
    if not inspect.iscoroutinefunction(HomGarClient.ensure_logged_in):
        print('API_CLIENT_TEST:FAIL:ensure_logged_in is not async')
    else:
        print('API_CLIENT_TEST:PASS')
" 2>/dev/null)

if [[ $API_CLIENT_TEST == "API_CLIENT_TEST:PASS" ]]; then
    echo "✅ API client methods test passed"
else
    echo "❌ ERROR: API client methods test failed"
    echo "Result: $API_CLIENT_TEST"
    exit 1
fi

# Test Display Hub decoder
echo "🧪 Testing Display Hub decoder..."
cat > /tmp/test_display_hub.py << 'PYEOF'
import sys
sys.path.insert(0, '/config')
from custom_components.homgar.homgar_api import decode_hws019wrf_v2

result = decode_hws019wrf_v2('1,136;781(781/723/1),52(64/50/1),P=10213(10222/10205/1),')
temp = result.get('temp_current_c')
hum = result.get('humidity_current')
press = result.get('pressure_current_hpa')
temp_high = result.get('temp_high_c')
hum_low = result.get('humidity_low')

expected_temp = round((781/10.0 - 32.0)*5.0/9.0, 1)
expected_press = round(10213/10.0, 1)

if temp == expected_temp and hum == 52 and press == expected_press and temp_high is not None and hum_low is not None:
    print('DISPLAY_HUB_TEST:PASS')
else:
    print(f'DISPLAY_HUB_TEST:FAIL:temp={temp}(exp {expected_temp}),hum={hum},press={press}(exp {expected_press}),temp_high={temp_high},hum_low={hum_low}')
PYEOF
docker cp /tmp/test_display_hub.py ha-test:/tmp/test_display_hub.py
DISPLAY_HUB_TEST=$(docker exec ha-test python3 /tmp/test_display_hub.py 2>/dev/null)

if [[ $DISPLAY_HUB_TEST == "DISPLAY_HUB_TEST:PASS" ]]; then
    echo "✅ Display Hub decoder test passed"
else
    echo "❌ ERROR: Display Hub decoder test failed"
    echo "Result: $DISPLAY_HUB_TEST"
    exit 1
fi

# Test translation files exist and are valid JSON
echo "🧪 Testing translation files..."
TRANSLATION_TEST=$(docker exec ha-test python3 -c "
import sys
import json
sys.path.append('/config/custom_components')

try:
    with open('/config/custom_components/homgar/translations/en.json', 'r') as f:
        translations = json.load(f)
    
    # Check critical keys exist
    if 'config' not in translations:
        print('TRANSLATION_TEST:FAIL:Missing config key')
    elif 'step' not in translations['config']:
        print('TRANSLATION_TEST:FAIL:Missing step key')
    elif 'user' not in translations['config']['step']:
        print('TRANSLATION_TEST:FAIL:Missing user step')
    else:
        print('TRANSLATION_TEST:PASS')
except json.JSONDecodeError as e:
    print(f'TRANSLATION_TEST:FAIL:Invalid JSON: {e}')
except Exception as e:
    print(f'TRANSLATION_TEST:FAIL:{e}')
" 2>/dev/null)

if [[ $TRANSLATION_TEST == "TRANSLATION_TEST:PASS" ]]; then
    echo "✅ Translation files test passed"
else
    echo "❌ ERROR: Translation files test failed"
    echo "Result: $TRANSLATION_TEST"
    exit 1
fi

# Test cold import of api module (catches missing imports that module cache can hide)
echo "🧪 Testing cold import of api module..."
COLD_IMPORT_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.insert(0, '/config/custom_components')
# Force fresh import with no cache
import importlib
import custom_components.homgar.api as api_mod
importlib.reload(api_mod)
# Verify every name in __all__ is actually importable
missing = [name for name in api_mod.__all__ if not hasattr(api_mod, name)]
if missing:
    print(f'COLD_IMPORT_TEST:FAIL:Missing from __all__: {missing}')
else:
    print('COLD_IMPORT_TEST:PASS')
" 2>/dev/null)

if [[ $COLD_IMPORT_TEST == "COLD_IMPORT_TEST:PASS" ]]; then
    echo "✅ Cold import test passed"
else
    echo "❌ ERROR: Cold import test failed"
    echo "Result: $COLD_IMPORT_TEST"
    exit 1
fi

# Test coordinator data structure
echo "🧪 Testing coordinator data structure..."
COORDINATOR_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.append('/config/custom_components')
from custom_components.homgar.coordinator import HomGarCoordinator, DECODER_REGISTRY
from custom_components.homgar.const import (
    MODEL_MOISTURE_SIMPLE, MODEL_MOISTURE_FULL, MODEL_RAIN,
    MODEL_TEMPHUM, MODEL_FLOWMETER, MODEL_CO2, MODEL_POOL,
    MODEL_VALVE_213, MODEL_HCS0528ARF, MODEL_HCS0565ARF,
)

# Verify critical models are registered
required = [
    MODEL_MOISTURE_SIMPLE, MODEL_MOISTURE_FULL, MODEL_RAIN,
    MODEL_TEMPHUM, MODEL_FLOWMETER, MODEL_CO2, MODEL_POOL,
    MODEL_VALVE_213, MODEL_HCS0528ARF, MODEL_HCS0565ARF,
]
missing = [m for m in required if m not in DECODER_REGISTRY]
if missing:
    print(f'COORDINATOR_TEST:FAIL:Missing decoders: {missing}')
else:
    print('COORDINATOR_TEST:PASS')" 2>/dev/null)

if [[ $COORDINATOR_TEST == "COORDINATOR_TEST:PASS" ]]; then
    echo "✅ Coordinator decoder registry test passed"
else
    echo "❌ ERROR: Coordinator decoder registry test failed"
    echo "Result: $COORDINATOR_TEST"
    exit 1
fi

# Test EU ASCII format decoders (issue #29 — HCS014ARF, HCS012ARF, HWS388WRF-V13)
echo "🧪 Testing EU ASCII format decoders..."
cp scripts/test_eu_decoders.py /tmp/test_eu_decoders.py 2>/dev/null || true
docker cp scripts/test_eu_decoders.py ha-test:/tmp/test_eu_decoders.py > /dev/null 2>&1
EU_TEST=$(docker exec ha-test python3 /tmp/test_eu_decoders.py 2>/dev/null | tail -1)

if [[ $EU_TEST == "EU_DECODER_TEST:PASS" ]]; then
    echo "✅ EU ASCII format decoder test passed"
else
    echo "❌ ERROR: EU ASCII format decoder test failed"
    docker exec ha-test python3 /tmp/test_eu_decoders.py 2>/dev/null
    exit 1
fi

# Test HWS388WRF-V13 is in coordinator decoder registry
echo "🧪 Testing HWS388WRF-V13 in decoder registry..."
HWS388_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.append('/config/custom_components')
from custom_components.homgar.coordinator import DECODER_REGISTRY
from custom_components.homgar.const import MODEL_HWS388WRF_V13
if MODEL_HWS388WRF_V13 in DECODER_REGISTRY:
    print('HWS388_TEST:PASS')
else:
    print('HWS388_TEST:FAIL:not in DECODER_REGISTRY')
" 2>/dev/null)

if [[ $HWS388_TEST == "HWS388_TEST:PASS" ]]; then
    echo "✅ HWS388WRF-V13 decoder registry test passed"
else
    echo "❌ ERROR: HWS388WRF-V13 not registered"
    echo "Result: $HWS388_TEST"
    exit 1
fi

# Test pool sensor decoder produces correct output keys
echo "🧪 Testing HCS0528ARF pool decoder output keys..."
POOL_DECODER_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.append('/config/custom_components')
from custom_components.homgar.homgar_api import decode_hcs0528arf
result = decode_hcs0528arf('10#E74A03B403DC01B805859003FF0F99620F19')
temp = result.get('tempcurrent')
high = result.get('temphigh')
low = result.get('templow')
# App shows: current=32.9, high=34.9, low=29.0
if temp is not None and abs(temp - 32.9) < 0.15 and high is not None and low is not None:
    print(f'POOL_TEST:PASS:{temp}')
else:
    print(f'POOL_TEST:FAIL:tempcurrent={temp},temphigh={high},templow={low}')" 2>/dev/null)

if [[ $POOL_DECODER_TEST == POOL_TEST:PASS* ]]; then
    echo "✅ Pool decoder test passed: $POOL_DECODER_TEST"
else
    echo "❌ ERROR: Pool decoder test failed"
    echo "Result: $POOL_DECODER_TEST"
    exit 1
fi

echo "🎉 All Docker tests passed! Commit allowed."
exit 0
