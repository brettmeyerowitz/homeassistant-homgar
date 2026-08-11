"""Telemetry payload/guard tests (v3.0.44, opt-in telemetry).

Pure-logic coverage for the pieces that decide WHAT is sent and WHETHER to
send. The privacy-relevant assertions are the point: the payload must never
carry a field outside the permitted set, and must omit `models` entirely
when models are not opted in.

Runs in the ha-test container against the deployed integration at /config.
"""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/config")

from custom_components.homgar.telemetry import (  # noqa: E402
    build_payload,
    models_from_coordinator_data,
    should_ping,
    is_telemetry_enabled,
    PING_INTERVAL_HOURS,
    TELEMETRY_URL,
)
from custom_components.homgar.const import (  # noqa: E402
    CONF_TELEMETRY_CHOICE,
    CONF_TELEMETRY_COUNTRY,
    CONF_TELEMETRY_MODELS,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


ID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
PERMITTED = {
    "anon_id", "integration_version", "hass_version",
    "share_country", "share_models", "models",
}

# --- payload shape ---------------------------------------------------------
full = build_payload(ID, "3.0.44", "2026.8.1", True, True, ["HTV245FRF"])
check("payload has no field outside the permitted set",
      set(full) <= PERMITTED, f"extra: {set(full) - PERMITTED}")
check("payload carries the anon id", full["anon_id"] == ID)
check("payload carries both versions",
      full["integration_version"] == "3.0.44" and full["hass_version"] == "2026.8.1")
check("flags are real booleans, not truthy values",
      full["share_country"] is True and full["share_models"] is True)

no_models = build_payload(ID, "3.0.44", "2026.8.1", True, False, ["HTV245FRF"])
check("models key is OMITTED entirely when not opted in",
      "models" not in no_models, f"got {no_models!r}")
check("share_models is still present and False", no_models["share_models"] is False)

no_country = build_payload(ID, "3.0.44", "2026.8.1", False, True, ["HTV245FRF"])
check("share_country False is sent explicitly", no_country["share_country"] is False)

# The client must never send location itself — the worker derives country at
# the edge. Any location-shaped key here would be a privacy regression.
for forbidden in ("country", "city", "latitude", "longitude", "postal_code",
                  "timezone", "region", "ip", "email", "home_name"):
    check(f"payload never contains '{forbidden}'", forbidden not in full)

# --- model extraction ------------------------------------------------------
DATA = {"hubs": [
    {"model": "HWG023WBRF-V2", "subDevices": [
        {"model": "HTV245FRF"}, {"model": "HTV245FRF"}, {"model": None},
    ]},
    {"model": "HWG023WBRF-V2", "subDevices": [{"model": "HCS012ARF"}]},
]}
models = models_from_coordinator_data(DATA)
check("model list is deduplicated and sorted",
      models == ["HCS012ARF", "HTV245FRF", "HWG023WBRF-V2"], f"got {models}")
check("None models are dropped", None not in models)
check("empty data yields an empty list", models_from_coordinator_data({}) == [])

# --- daily guard -----------------------------------------------------------
now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
check("pings when never pinged before", should_ping(None, now, PING_INTERVAL_HOURS) is True)
check("does not ping 1h after the last ping",
      should_ping(now - timedelta(hours=1), now, PING_INTERVAL_HOURS) is False)
check("does not ping at 23h59m",
      should_ping(now - timedelta(hours=23, minutes=59), now, PING_INTERVAL_HOURS) is False)
check("pings at 24h01m",
      should_ping(now - timedelta(hours=24, minutes=1), now, PING_INTERVAL_HOURS) is True)
check("a corrupt last_ping_at does not crash and allows a ping",
      should_ping("not-a-timestamp", now, PING_INTERVAL_HOURS) is True)
check("a future last_ping_at (clock skew) does not ping forever",
      should_ping(now + timedelta(days=400), now, PING_INTERVAL_HOURS) is False)

# --- enablement ------------------------------------------------------------
check("disabled when nothing is set", is_telemetry_enabled({}) is False)
check("disabled when explicitly off",
      is_telemetry_enabled({CONF_TELEMETRY_CHOICE: False}) is False)
check("enabled only when master is on",
      is_telemetry_enabled({CONF_TELEMETRY_CHOICE: True}) is True)
check("sub-toggles alone never enable telemetry",
      is_telemetry_enabled({CONF_TELEMETRY_COUNTRY: True,
                            CONF_TELEMETRY_MODELS: True}) is False)

check("endpoint is the deployed worker over https",
      TELEMETRY_URL.startswith("https://") and TELEMETRY_URL.endswith("/ping"),
      TELEMETRY_URL)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
