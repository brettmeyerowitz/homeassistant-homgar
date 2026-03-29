#!/bin/bash

# Pre-commit Docker testing script
# This script runs Docker testing before allowing commits

set -e

echo "🔍 Running pre-commit Docker testing..."

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
if docker logs ha-test 2>&1 | grep -q "Setup failed for custom integration 'homgar'"; then
    echo "❌ ERROR: Integration setup failed in Docker"
    echo "Error details:"
    docker logs ha-test 2>&1 | grep "Setup failed for custom integration 'homgar'" -A 5
    exit 1
fi

# Check for missing dependencies
if docker logs ha-test 2>&1 | grep -q "No module named"; then
    echo "❌ ERROR: Missing dependencies in Docker"
    echo "Error details:"
    docker logs ha-test 2>&1 | grep "No module named" -A 2
    exit 1
fi

# Verify version is loaded
echo "🔍 Verifying version is loaded..."
VERSION=$(grep "VERSION = " custom_components/homgar/const.py | cut -d'"' -f2)
if docker logs ha-test 2>&1 | grep -q "HomGar v$VERSION"; then
    echo "✅ Version $VERSION loaded successfully"
else
    echo "❌ ERROR: Version $VERSION not found in Docker logs"
    echo "Expected: HomGar v$VERSION"
    echo "Found in logs:"
    docker logs ha-test 2>&1 | grep "HomGar v" | tail -3
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
print(f'SENSOR_TEST:{result[\"decoder\"]}:{result[\"temperature_c\"]}')
" 2>/dev/null)

if [[ $SENSOR_TEST_RESULT == "SENSOR_TEST:hcs021frf_ascii:69.4" ]]; then
    echo "✅ Sensor ASCII format decoding test passed"
else
    echo "❌ ERROR: Sensor ASCII format decoding test failed"
    echo "Expected: SENSOR_TEST:hcs021frf_ascii:69.4"
    echo "Got: $SENSOR_TEST_RESULT"
    exit 1
fi

echo "🎉 All Docker tests passed! Commit allowed."
exit 0
