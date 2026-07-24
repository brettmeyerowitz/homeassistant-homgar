"""Token diagnostic sensor tests. Runs in the ha-test container against the
deployed integration at /config (imports Home Assistant)."""
import sys
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/config")

from custom_components.homgar.const import DOMAIN  # noqa: E402

from custom_components.homgar.diagnostic_token_sensors import (  # noqa: E402
    HomGarTokenReauthCountSensor,
    HomGarLastTokenReauthSensor,
    HomGarTokenExpiresAtSensor,
    build_token_diagnostic_sensors,
)
from homeassistant.components.sensor import SensorStateClass, SensorDeviceClass  # noqa: E402
from homeassistant.const import EntityCategory  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


now = datetime.now(timezone.utc)
expires = now + timedelta(days=38)
client = types.SimpleNamespace(
    reauth_count=7,
    last_reauth_at=now,
    last_reauth_trigger="subscribeStatus",
    last_reauth_code=1001,
    token_expires_at=expires,
)
coordinator = types.SimpleNamespace(_client=client, data={"hubs": []}, last_update_success=True)
hub_info = {"mid": 12345, "name": "Hub", "model": "HWG023WBRF-V2"}
ENTRY = "entry_abc"

count = HomGarTokenReauthCountSensor(coordinator, hub_info, ENTRY)
last = HomGarLastTokenReauthSensor(coordinator, hub_info, ENTRY)
exp = HomGarTokenExpiresAtSensor(coordinator, hub_info, ENTRY)

check("count native_value reads reauth_count", count.native_value == 7, f"got {count.native_value}")
check("count is total_increasing", count.state_class == SensorStateClass.TOTAL_INCREASING)
check("count is DIAGNOSTIC", count.entity_category == EntityCategory.DIAGNOSTIC)
check("count enabled by default", count.entity_registry_enabled_default is True)
check("count unique_id is entry-scoped",
      count.unique_id == f"{ENTRY}_token_reauth_count", f"got {count.unique_id}")
check("count attaches to hub device",
      (DOMAIN, f"rainpoint_hub_12345") in count.device_info["identifiers"])

check("last native_value is the reauth timestamp", last.native_value == now)
check("last is timestamp device_class", last.device_class == SensorDeviceClass.TIMESTAMP)
check("last exposes trigger attr",
      last.extra_state_attributes.get("trigger_endpoint") == "subscribeStatus")
check("last exposes error code attr",
      last.extra_state_attributes.get("last_error_code") == 1001)

check("expires native_value is token_expires_at", exp.native_value == expires)
check("expires is timestamp device_class", exp.device_class == SensorDeviceClass.TIMESTAMP)

built = build_token_diagnostic_sensors(coordinator, hub_info, ENTRY)
check("factory returns exactly 3 sensors", len(built) == 3, f"got {len(built)}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
