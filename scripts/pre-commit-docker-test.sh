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
from custom_components.homgar.homgar_api import decode_htv213frf_valve
result = decode_htv213frf_valve('1,-84,1;0,149,0,0,0,0|0,6,0,0,0,0')
print(f'ASCII_TEST:{result[\"decoder\"]}:{len(result[\"zones\"])}')
" 2>/dev/null)

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
from custom_components.homgar.homgar_api import decode_moisture_full
result = decode_moisture_full('1,-73,1;694,70,G=292478')
# Test temperature is in expected range (20.77-20.78°C for 69.4°F)
temp = result['temperature_c']
if 20.77 <= temp <= 20.79:
    print('SENSOR_TEST:hcs021frf_ascii:PASS')
else:
    print(f'SENSOR_TEST:hcs021frf_ascii:FAIL:{temp}')
" 2>/dev/null)

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
DISPLAY_HUB_TEST=$(docker exec ha-test python3 -c "
import sys
sys.path.append('/config/custom_components')
from custom_components.homgar.homgar_api import decode_hws019wrf_v2

# Test with real payload format
result = decode_hws019wrf_v2('1,0,1;707(707/694/1),42(42/39/1),P=9709(9709/9701/1),')
readings = result.get('readings', {})

# Check that values are extracted correctly (not raw strings with parentheses)
temp = readings.get('temp', '')
humidity = readings.get('humidity', '')
pressure = readings.get('P', '')

if temp == '707' and humidity == '42' and pressure == '9709':
    print('DISPLAY_HUB_TEST:PASS')
else:
    print(f'DISPLAY_HUB_TEST:FAIL:temp={temp},humidity={humidity},pressure={pressure}')
" 2>/dev/null)

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

echo "🎉 All Docker tests passed! Commit allowed."
exit 0
