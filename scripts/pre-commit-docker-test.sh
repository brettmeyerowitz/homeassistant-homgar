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

# Check HA log file (HA logs to file, not stdout)
# Use more lines since log accumulates across restarts
RECENT_LOGS=$(docker exec ha-test tail -1000 /config/home-assistant.log 2>&1)

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

# ── Test: API client critical methods ─────────────────────────────────────
echo "🧪 Testing API client methods..."
cat > /tmp/test_api.py << 'PYEOF'
import sys, inspect
sys.path.insert(0, '/config')
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
PYEOF
docker cp /tmp/test_api.py ha-test:/tmp/test_api.py > /dev/null
API_TEST=$(docker exec ha-test python3 /tmp/test_api.py 2>/dev/null)

if [[ $API_TEST == "API_TEST:PASS" ]]; then
    echo "✅ API client methods present"
else
    echo "❌ ERROR: API client check failed"
    echo "Result: $API_TEST"
    exit 1
fi

# ── Test: translation files valid ─────────────────────────────────────────
echo "🧪 Testing translation files..."
cat > /tmp/test_translations.py << 'PYEOF'
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
PYEOF
docker cp /tmp/test_translations.py ha-test:/tmp/test_translations.py > /dev/null
TRANSLATION_TEST=$(docker exec ha-test python3 /tmp/test_translations.py 2>/dev/null)

if [[ $TRANSLATION_TEST == "TRANSLATION_TEST:PASS" ]]; then
    echo "✅ Translation files valid"
else
    echo "❌ ERROR: Translation files invalid"
    echo "Result: $TRANSLATION_TEST"
    exit 1
fi

# ── Test: config flow account identity logic ──────────────────────────────
echo "🧪 Testing config flow account identity logic..."
cat > /tmp/test_config_flow_identity.py << 'PYEOF'
import sys
from types import SimpleNamespace

sys.path.insert(0, '/config')

from custom_components.homgar.config_flow import (
    _build_account_unique_id,
    _entry_matches_account,
)

legacy_entry = SimpleNamespace(data={
    "email": "user@example.com",
    "area_code": "1",
})
homgar_entry = SimpleNamespace(data={
    "email": "user@example.com",
    "area_code": "1",
    "app_type": "homgar",
})
rainpoint_entry = SimpleNamespace(data={
    "email": "user@example.com",
    "area_code": "1",
    "app_type": "rainpoint",
})

if _build_account_unique_id("1", "User@Example.com", "homgar") == _build_account_unique_id("1", "user@example.com", "rainpoint"):
    print("CONFIG_FLOW_TEST:FAIL:unique_id_collision")
elif not _entry_matches_account(legacy_entry, "1", "USER@example.com", "homgar"):
    print("CONFIG_FLOW_TEST:FAIL:legacy_match")
elif _entry_matches_account(homgar_entry, "1", "user@example.com", "rainpoint"):
    print("CONFIG_FLOW_TEST:FAIL:app_type_separation")
elif not _entry_matches_account(rainpoint_entry, "1", "user@example.com", "rainpoint"):
    print("CONFIG_FLOW_TEST:FAIL:rainpoint_match")
else:
    print("CONFIG_FLOW_TEST:PASS")
PYEOF
docker cp /tmp/test_config_flow_identity.py ha-test:/tmp/test_config_flow_identity.py > /dev/null
CONFIG_FLOW_TEST=$(docker exec ha-test python3 /tmp/test_config_flow_identity.py 2>/dev/null)

if [[ $CONFIG_FLOW_TEST == "CONFIG_FLOW_TEST:PASS" ]]; then
    echo "✅ Config flow account identity logic passed"
else
    echo "❌ ERROR: Config flow account identity logic failed"
    echo "Result: $CONFIG_FLOW_TEST"
    exit 1
fi

# ── Test: fixture-driven payload corpus ───────────────────────────────────
echo "🧪 Running fixture-driven payload corpus..."
docker cp tests/fixtures ha-test:/tmp/tests/ > /dev/null
docker cp tests/run_payload_fixture_tests.py ha-test:/tmp/tests/run_payload_fixture_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_payload_fixture_tests.py; then
    echo "✅ Fixture-driven payload corpus passed"
else
    echo "❌ ERROR: Fixture-driven payload corpus failed"
    exit 1
fi

# ── Test: MQTT parser regressions ─────────────────────────────────────────
echo "🧪 Running MQTT parser regression tests..."
docker cp tests/run_mqtt_parser_tests.py ha-test:/tmp/tests/run_mqtt_parser_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_mqtt_parser_tests.py; then
    echo "✅ MQTT parser regression tests passed"
else
    echo "❌ ERROR: MQTT parser regression tests failed"
    exit 1
fi

# ── Test: MQTT routing regressions ────────────────────────────────────────
echo "🧪 Running MQTT routing regression tests..."
docker cp tests/run_mqtt_routing_tests.py ha-test:/tmp/tests/run_mqtt_routing_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_mqtt_routing_tests.py; then
    echo "✅ MQTT routing regression tests passed"
else
    echo "❌ ERROR: MQTT routing regression tests failed"
    exit 1
fi

# ── Test: zone label regressions ──────────────────────────────────────────
echo "🧪 Running zone label regression tests..."
docker cp tests/run_zone_label_tests.py ha-test:/tmp/tests/run_zone_label_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_zone_label_tests.py; then
    echo "✅ Zone label regression tests passed"
else
    echo "❌ ERROR: Zone label regression tests failed"
    exit 1
fi

# ── Test: decoder regression suite (scripts/test_decoders.py) ─────────────
echo "🧪 Running decoder regression suite..."
docker cp scripts/test_decoders.py ha-test:/tmp/test_decoders.py > /dev/null
if docker exec ha-test python3 /tmp/test_decoders.py; then
    echo "✅ Decoder regression suite passed"
else
    echo "❌ ERROR: Decoder regression suite failed"
    exit 1
fi

echo ""
echo "🎉 All pre-commit tests passed! Commit allowed."
exit 0
