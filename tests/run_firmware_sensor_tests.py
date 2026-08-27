"""Regression tests: no phantom Firmware Version entity (issue #92).

RF accessories such as the HCS012ARF rain gauge have no independently
flashable firmware. The API reports ``softVer`` as 0 for them, and we created
a Firmware Version sensor for every sub-device unconditionally - so those
devices showed a permanent "Firmware Version 0" that the HomGar app does not
show at all. The hub path already guarded this with ``or None``; the
sub-device path did not.

An entity that can only ever read 0, or Unknown, is worse than no entity: it
invites people to treat it as a real reading, exactly as the phantom
"0 dBm" signal sensor did on the same device.

This is entity-wiring rather than decoding, which is the category that has
bitten us before - a clean import proves nothing about what gets created. So
these tests drive the real ``async_setup_entry`` and count what comes out.

Runs in the ha-test container, where Home Assistant is importable.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    for start in (Path(__file__).resolve().parent, Path.cwd(), Path("/config")):
        current = start
        while True:
            if (current / "custom_components" / "homgar" / "sensor.py").exists():
                return current
            if current.parent == current:
                break
            current = current.parent
    raise RuntimeError("Could not locate repository root")


ROOT = _find_repo_root()

try:
    import homeassistant  # noqa: F401
except ImportError:
    print("⏭  Home Assistant not importable - run this in the ha-test container.")
    sys.exit(0)

sys.path.insert(0, str(ROOT))
from custom_components.homgar import sensor as sensor_mod  # noqa: E402
from custom_components.homgar.const import DOMAIN  # noqa: E402
from custom_components.homgar.diagnostic_sensors import (  # noqa: E402
    HomGarFirmwareVersionSensor,
)

PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  ✅ %s" % label)
    else:
        FAIL += 1
        print("  ❌ %s%s" % (label, (" — %s" % detail) if detail else ""))


class _Coordinator:
    """Enough of the coordinator for entity construction."""

    def __init__(self, sensors):
        self.data = {"sensors": sensors, "hubs": []}
        self.last_update_success = True

    def async_add_listener(self, *_a, **_kw):
        return lambda: None


class _Entry:
    entry_id = "test_entry"
    options: dict = {}
    data: dict = {}


class _Hass:
    def __init__(self, coordinator):
        self.data = {DOMAIN: {_Entry.entry_id: {"coordinator": coordinator}}}


def _sub(firmware):
    """A minimal single-port sub-device record."""
    return {
        "sub_name": "Rain Sensor",
        "model": "HCS012ARF",
        "firmware_version": firmware,
        "data": {"port_number": 1, "precipitation_total": 660.0},
    }


def _build(sensors):
    coordinator = _Coordinator(sensors)
    created: list = []

    def add(entities, *_a, **_kw):
        created.extend(entities)

    asyncio.run(sensor_mod.async_setup_entry(_Hass(coordinator), _Entry(), add))
    return created


def _firmware_entities(created):
    return [e for e in created if isinstance(e, HomGarFirmwareVersionSensor)]


print("\n🧪 Firmware Version entity creation")

created = _build({"dev_no_fw": _sub(None)})
check("absent firmware -> no entity", len(_firmware_entities(created)) == 0,
      "got %d" % len(_firmware_entities(created)))

created = _build({"dev_zero_fw": _sub(0)})
check("softVer 0 -> no entity", len(_firmware_entities(created)) == 0,
      "got %d" % len(_firmware_entities(created)))

created = _build({"dev_empty_fw": _sub("")})
check("empty firmware string -> no entity", len(_firmware_entities(created)) == 0,
      "got %d" % len(_firmware_entities(created)))

# The API returns softVer as a string for some accounts, so "0" must be
# rejected as firmly as the integer 0 - `or None` only catches the integer,
# which is how "Firmware Version 0" survived the first attempt at this fix.
for junk in ("0", "0.0", " 0 ", "none", "null", "  "):
    created = _build({"dev_str_fw": _sub(junk)})
    check("softVer %r -> no entity" % junk,
          len(_firmware_entities(created)) == 0,
          "got %d" % len(_firmware_entities(created)))

created = _build({"dev_real_fw": _sub("1.1.1041")})
fw = _firmware_entities(created)
check("real firmware -> entity created", len(fw) == 1, "got %d" % len(fw))
if fw:
    check("entity reports the version", fw[0].native_value == "1.1.1041",
          str(fw[0].native_value))

# A device without firmware must not lose its other entities.
created = _build({"dev_no_fw": _sub(None)})
check("other entities still created", len(created) > 0, "got %d" % len(created))

# Mixed account: only the device that reports firmware gets the sensor.
created = _build({"dev_no_fw": _sub(None), "dev_real_fw": _sub("2.0.1")})
check("mixed account -> exactly one firmware entity",
      len(_firmware_entities(created)) == 1,
      "got %d" % len(_firmware_entities(created)))

print("\n" + "=" * 50)
print("Firmware sensor results: %d/%d passed, %d failed" % (PASS, PASS + FAIL, FAIL))
sys.exit(1 if FAIL else 0)
