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

# Ensure HomGar setup completion is detectable. HA does not emit an INFO-level
# "Setup of domain homgar took" line on current versions, and this container's
# default log level suppresses INFO, so we poll for HomGar's own completion
# marker and make sure that logger is at INFO. Idempotent; skipped if the config
# already defines a logger block.
if ! docker exec ha-test grep -q "custom_components.homgar" /config/configuration.yaml 2>/dev/null; then
    if docker exec ha-test grep -q "^logger:" /config/configuration.yaml 2>/dev/null; then
        echo "⚠️  Existing logger: block found; not modifying. Setup detection relies on it exposing custom_components.homgar at INFO."
    else
        echo "🔧 Enabling custom_components.homgar INFO logging for setup detection..."
        docker exec ha-test sh -c 'printf "\nlogger:\n  default: warning\n  logs:\n    custom_components.homgar: info\n" >> /config/configuration.yaml'
    fi
fi

# Markers that indicate HomGar finished setting up (new HA emits the first; the
# legacy HA-core string is kept as a fallback for older versions).
SETUP_MARKER="Completed platform setup for entry|Setup of domain homgar took"

echo "🔄 Restarting Docker container..."
docker restart ha-test > /dev/null 2>&1
echo "⏳ Waiting for HA to start..."
SETUP_FOUND=0
for i in {1..24}; do
    sleep 5
    if docker exec ha-test tail -1000 /config/home-assistant.log 2>&1 | grep -qE "$SETUP_MARKER"; then
        SETUP_FOUND=1
        break
    fi
done

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
if [ "$SETUP_FOUND" -eq 1 ] || echo "$RECENT_LOGS" | grep -qE "$SETUP_MARKER"; then
    echo "✅ HomGar integration setup successfully"
else
    echo "❌ ERROR: Integration did not set up within 120s"
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
# Create /tmp/tests first so `docker cp tests/fixtures` nests into
# /tmp/tests/fixtures. Without this, a first run on a fresh container copies the
# fixtures directory *as* /tmp/tests, so the test can't find fixtures/ beside it.
docker exec ha-test mkdir -p /tmp/tests
docker cp tests/fixtures ha-test:/tmp/tests/ > /dev/null
docker cp tests/run_payload_fixture_tests.py ha-test:/tmp/tests/run_payload_fixture_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_payload_fixture_tests.py; then
    echo "✅ Fixture-driven payload corpus passed"
else
    echo "❌ ERROR: Fixture-driven payload corpus failed"
    exit 1
fi

# ── Test: area seeding regressions ────────────────────────────────────────
echo "🧪 Running area seeding regression tests..."
docker cp tests/run_area_seeding_tests.py ha-test:/tmp/tests/run_area_seeding_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_area_seeding_tests.py; then
    echo "✅ Area seeding regression tests passed"
else
    echo "❌ ERROR: Area seeding regression tests failed"
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

# ── Test: zone device regressions ─────────────────────────────────────────
echo "🧪 Running zone device regression tests..."
docker cp tests/run_zone_device_tests.py ha-test:/tmp/tests/run_zone_device_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_zone_device_tests.py; then
    echo "✅ Zone device regression tests passed"
else
    echo "❌ ERROR: Zone device regression tests failed"
    exit 1
fi

# ── Test: duration unit option regressions ─────────────────────────────────
echo "🧪 Running duration unit regression tests..."
docker cp tests/run_duration_unit_tests.py ha-test:/tmp/tests/run_duration_unit_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_duration_unit_tests.py; then
    echo "✅ Duration unit regression tests passed"
else
    echo "❌ ERROR: Duration unit regression tests failed"
    exit 1
fi

# ── Test: BLE/DP valve control regressions ─────────────────────────────────
echo "🧪 Running BLE/DP valve control regression tests..."
docker cp tests/run_ble_valve_model_tests.py ha-test:/tmp/tests/run_ble_valve_model_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_ble_valve_model_tests.py; then
    echo "✅ BLE/DP valve control regression tests passed"
else
    echo "❌ ERROR: BLE/DP valve control regression tests failed"
    exit 1
fi

# ── Test: User-Agent regressions ──────────────────────────────────────────
echo "🧪 Running User-Agent regression tests..."
docker cp tests/run_user_agent_tests.py ha-test:/tmp/tests/run_user_agent_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_user_agent_tests.py; then
    echo "✅ User-Agent regression tests passed"
else
    echo "❌ ERROR: User-Agent regression tests failed"
    exit 1
fi

# ── Test: token re-auth / retry regressions ───────────────────────────────
echo "🧪 Running token re-auth regression tests..."
docker cp tests/run_token_reauth_tests.py ha-test:/tmp/tests/run_token_reauth_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_token_reauth_tests.py; then
    echo "✅ Token re-auth regression tests passed"
else
    echo "❌ ERROR: Token re-auth regression tests failed"
    exit 1
fi

# ── Test: token telemetry + sensor regressions ────────────────────────────
echo "🧪 Running token telemetry tests..."
docker cp tests/run_token_diag_tests.py ha-test:/tmp/tests/run_token_diag_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_token_diag_tests.py; then
    echo "✅ Token telemetry tests passed"
else
    echo "❌ ERROR: Token telemetry tests failed"
    exit 1
fi

echo "🧪 Running token diagnostic sensor tests..."
docker cp tests/run_token_sensor_tests.py ha-test:/tmp/run_token_sensor_tests.py > /dev/null
if docker exec ha-test python3 /tmp/run_token_sensor_tests.py; then
    echo "✅ Token diagnostic sensor tests passed"
else
    echo "❌ ERROR: Token diagnostic sensor tests failed"
    exit 1
fi

# ── Test: transient-error retry/backoff (issue #82) ───────────────────────
echo "🧪 Running transient-error retry tests..."
docker cp tests/run_transient_retry_tests.py ha-test:/tmp/tests/run_transient_retry_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_transient_retry_tests.py; then
    echo "✅ Transient-error retry tests passed"
else
    echo "❌ ERROR: Transient-error retry tests failed"
    exit 1
fi

# ── Test: coordinator last-good retention (issue #82) ─────────────────────
echo "🧪 Running coordinator retention tests..."
docker cp tests/run_coordinator_retention_tests.py ha-test:/tmp/run_coordinator_retention_tests.py > /dev/null
if docker exec ha-test python3 /tmp/run_coordinator_retention_tests.py; then
    echo "✅ Coordinator retention tests passed"
else
    echo "❌ ERROR: Coordinator retention tests failed"
    exit 1
fi

# ── Test: ppm unit constant (issue #84) ───────────────────────────────────
echo "🧪 Running ppm unit constant tests..."
docker cp tests/run_ppm_unit_tests.py ha-test:/tmp/tests/run_ppm_unit_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_ppm_unit_tests.py; then
    echo "✅ ppm unit constant tests passed"
else
    echo "❌ ERROR: ppm unit constant tests failed"
    exit 1
fi

# ── Test: home-name retention (issue #82 follow-up) ───────────────────────
echo "🧪 Running home-name retention tests..."
docker cp tests/run_home_name_retention_tests.py ha-test:/tmp/tests/run_home_name_retention_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_home_name_retention_tests.py; then
    echo "✅ Home-name retention tests passed"
else
    echo "❌ ERROR: Home-name retention tests failed"
    exit 1
fi

# ── Test: write-path pre-send retry (issue #82 follow-up) ─────────────────
echo "🧪 Running write-path pre-send retry tests..."
docker cp tests/run_write_presend_retry_tests.py ha-test:/tmp/tests/run_write_presend_retry_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_write_presend_retry_tests.py; then
    echo "✅ Write-path pre-send retry tests passed"
else
    echo "❌ ERROR: Write-path pre-send retry tests failed"
    exit 1
fi

# ── Test: opt-in telemetry (v3.0.44) ──────────────────────────────────────
for suite in run_telemetry_payload_tests run_telemetry_send_tests run_telemetry_optin_tests run_telemetry_options_flow_tests run_coordinator_telemetry_tests; do
    echo "🧪 Running ${suite}..."
    docker cp "tests/${suite}.py" "ha-test:/tmp/tests/${suite}.py" > /dev/null
    if docker exec ha-test python3 "/tmp/tests/${suite}.py"; then
        echo "✅ ${suite} passed"
    else
        echo "❌ ERROR: ${suite} failed"
        exit 1
    fi
done

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
