"""Regression test: a device the cloud lists but sends no status for still
appears in Home Assistant.

The decode loop walks the *status* response and looks each entry up in the
device list, so a sub-device with no status was never reached and never
appeared in any form. The user saw nothing at all - no device, no entity, no
error - and two people have now concluded their own setup was at fault when it
was not (#97, and a later discussion thread about an HCS048B, a Bluetooth
sensor whose readings never leave the phone and so never reach the cloud).

Registering from the device list instead means the device shows up with its
diagnostic entities and reads as present-but-not-reporting.

Runs in the ha-test container against the deployed integration at /config.
"""
import sys

sys.path.insert(0, "/config")

from custom_components.homgar.coordinator import (  # noqa: E402
    _listed_but_silent_entries,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


print("\n🧪 Listed-but-silent sub-devices")

HUB = {
    "hid": "h1",
    "name": "Garden Hub",
    "homeName": "My Home",
    "subDevices": [
        {"addr": 1, "name": "Flow Meter", "model": "HCS048B", "softVer": "1.0.5"},
        {"addr": 5, "name": "Soil Sensor", "model": "HCS021FRF", "softVer": "2.1.0"},
    ],
}

# Nothing decoded at all: both listed devices must be registered.
entries = _listed_but_silent_entries(HUB, "m1", {}, {})
check("a device with no status is registered", set(entries) == {"m1_1", "m1_5"},
      str(sorted(entries)))
check("the model is carried through", entries["m1_1"]["model"] == "HCS048B")
check("the name is carried through", entries["m1_1"]["sub_name"] == "Flow Meter")
check("it starts with no data rather than fabricated data",
      entries["m1_1"]["data"] == {}, str(entries["m1_1"]["data"]))
check("raw_status is None, not an empty payload",
      entries["m1_1"]["raw_status"] is None)

# A device that did decode this poll must not be overwritten with a blank.
already = {"m1_5": {"model": "HCS021FRF", "data": {"temperature": 21.5}}}
entries = _listed_but_silent_entries(HUB, "m1", already, {})
check("a device that reported is left untouched", set(entries) == {"m1_1"},
      str(sorted(entries)))

# Last-good data is reused so a device that has reported before does not lose
# its readings on a poll where the cloud omits it.
entries = _listed_but_silent_entries(HUB, "m1", {}, {"m1_5": {"temperature": 19.0}})
check("last-good readings are reused when present",
      entries["m1_5"]["data"] == {"temperature": 19.0},
      str(entries["m1_5"]["data"]))
check("a device with no history still gets an empty dict",
      entries["m1_1"]["data"] == {})

# Malformed input must not raise: a hub with no subDevices key, and a
# sub-device with no addr, are both things the cloud has actually sent.
check("a hub with no subDevices yields nothing",
      _listed_but_silent_entries({"hid": "h"}, "m1", {}, {}) == {})
check("a hub with null subDevices yields nothing",
      _listed_but_silent_entries({"subDevices": None}, "m1", {}, {}) == {})
check("a sub-device with no addr is skipped",
      _listed_but_silent_entries(
          {"subDevices": [{"name": "nameless"}]}, "m1", {}, {}) == {})

total = PASS + FAIL
print(f"\n{'=' * 50}")
print(f"Listed-but-silent results: {PASS}/{total} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
