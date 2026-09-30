"""Regression test: a registered device with no readings still produces entities.

Registering a listed-but-silent device in the coordinator is only half the fix.
If the sensor platform then creates nothing for an entry whose ``data`` is
empty, the device still does not appear and the user is no better off - which
is the assumption the coordinator change rests on and the part that was never
actually exercised.

This drives the real ``sensor.async_setup_entry`` and asserts that an entry
with no readings still yields its diagnostic entities, while fabricating no
measurement entities for readings that were never received.

Runs in the ha-test container against the deployed integration at /config.
"""
import asyncio
import sys
from types import SimpleNamespace

sys.path.insert(0, "/config")

from custom_components.homgar import sensor as sensor_mod  # noqa: E402
from custom_components.homgar.const import DOMAIN  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


SILENT_KEY = "m1_7"
TALKING_KEY = "m1_8"


def build(sensors):
    coordinator = SimpleNamespace(
        data={"hubs": [], "sensors": sensors},
        _entry=SimpleNamespace(options={}),
        async_add_listener=lambda *a, **k: (lambda: None),
    )
    entry = SimpleNamespace(entry_id="e1", options={})
    hass = SimpleNamespace(data={DOMAIN: {"e1": {"coordinator": coordinator}}})
    created = []
    asyncio.run(sensor_mod.async_setup_entry(hass, entry, created.extend))
    return created


def keys_of(entities, key):
    return [e for e in entities if getattr(e, "_sensor_key", None) == key]


def class_names(entities):
    return sorted({type(e).__name__ for e in entities})


# A device the cloud lists but never reports on: registered, no readings.
silent_entry = {
    "hid": "h1", "mid": "m1", "addr": 7,
    "home_name": "My Home", "hub_name": "Hub",
    "sub_name": "Flow Meter", "model": "HCS048B",
    "firmware_version": None, "raw_status": None,
    "data": {}, "type_flag": 0,
}

print("\n🧪 Entities for a registered device with no readings")

entities = build({SILENT_KEY: silent_entry})
mine = keys_of(entities, SILENT_KEY)

check("a silent device produces at least one entity", len(mine) > 0,
      "no entities means the device still does not appear in Home Assistant")
check("it gets its raw payload diagnostic",
      any(type(e).__name__ == "HomGarRawPayloadSensor" for e in mine),
      str(class_names(mine)))
check("it gets its MQTT diagnostics",
      any("Mqtt" in type(e).__name__ for e in mine), str(class_names(mine)))
check("no measurement entity is fabricated from absent readings",
      not any(type(e).__name__ == "HomGarGenericSensor" for e in mine),
      str(class_names(mine)))
check("no firmware entity when the device reported no version",
      not any(type(e).__name__ == "HomGarFirmwareVersionSensor" for e in mine),
      str(class_names(mine)))

# device_info is what actually puts it in the device registry - if this raises
# or returns nothing, the device does not appear however many entities exist.
try:
    info = mine[0].device_info if mine else None
    ok = bool(info) and bool(info.get("identifiers"))
    detail = str(info)
except Exception as err:  # noqa: BLE001
    ok, detail = False, f"raised {err!r}"
check("the entity carries device_info so the device registers", ok, detail)

# Contrast: the same device once it does report. The measurement entities that
# were absent above must now exist, proving their absence was the empty data
# and not something structural about the model.
talking_entry = dict(silent_entry, addr=8, data={"battery_level": 100, "signal_strength": -62})
entities = build({TALKING_KEY: talking_entry})
mine_talking = keys_of(entities, TALKING_KEY)
check("the same device with readings does gain measurement entities",
      any(type(e).__name__ == "HomGarGenericSensor" for e in mine_talking),
      str(class_names(mine_talking)))
check("a reporting device yields more entities than a silent one",
      len(mine_talking) > len(mine), f"{len(mine_talking)} vs {len(mine)}")

total = PASS + FAIL
print(f"\n{'=' * 50}")
print(f"Silent-device entity results: {PASS}/{total} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
