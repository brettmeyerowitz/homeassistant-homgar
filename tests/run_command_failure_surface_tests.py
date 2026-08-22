"""Regression tests: a failed control command reaches the user (issue #82).

The retry envelope decides how hard we try; this suite covers what happens when
we still lose. Three pieces of runtime code had no coverage until now — they
imported cleanly in the ha-test container, which only proves the imports
resolve, not that anything works:

  * diagnostic_command_sensors.py  — the quiet, automatable channel
  * the notification wiring in __init__.py — the loud channel
  * the write-failure callback contract between them and the client

The distinctions worth pinning are behavioural, not structural:

  * Writes only. A failed poll self-heals on the next coordinator cycle;
    notifying on it would train people to ignore the notification entirely.
  * One stable notification_id per entry, so a multi-minute brownout that kills
    several commands in a row REPLACES one notification instead of stacking
    half a dozen. This is the difference between a useful alert and spam.
  * The sensors read live client state rather than a snapshot, so a failure that
    happens between coordinator polls is visible immediately.

Runs stdlib-only, in the ha-test container or on the host.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path


def _find_repo_root() -> Path:
    for start in (Path(__file__).resolve().parent, Path.cwd(), Path("/config")):
        current = start
        while True:
            if (current / "custom_components" / "homgar" / "diagnostic_command_sensors.py").exists():
                return current
            if current.parent == current:
                break
            current = current.parent
    raise RuntimeError("Could not locate repository root")


ROOT = _find_repo_root()

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        print(f"  ✅ {name}")
        PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}")
        FAIL += 1


# --- stub just enough Home Assistant to import the sensor module -------------
# Real HA is importable in the ha-test container, but pulling in the full
# sensor/entity stack drags a running hass along with it. The module under test
# only needs the symbols it references at import time.

def _install_ha_stubs() -> None:
    if "homeassistant.components.sensor" in sys.modules:
        return
    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))

    components = types.ModuleType("homeassistant.components")
    sensor = types.ModuleType("homeassistant.components.sensor")

    class _SensorEntity:
        pass

    class _Enum(str):
        pass

    sensor.SensorEntity = _SensorEntity
    sensor.SensorDeviceClass = type("SensorDeviceClass", (), {"TIMESTAMP": _Enum("timestamp")})
    sensor.SensorStateClass = type(
        "SensorStateClass", (), {"TOTAL_INCREASING": _Enum("total_increasing")})
    components.sensor = sensor

    const = types.ModuleType("homeassistant.const")
    const.EntityCategory = type("EntityCategory", (), {"DIAGNOSTIC": _Enum("diagnostic")})

    helpers = types.ModuleType("homeassistant.helpers")
    dev_reg = types.ModuleType("homeassistant.helpers.device_registry")
    dev_reg.DeviceInfo = dict
    upd = types.ModuleType("homeassistant.helpers.update_coordinator")

    class _CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

    upd.CoordinatorEntity = _CoordinatorEntity
    upd.DataUpdateCoordinator = object
    upd.UpdateFailed = type("UpdateFailed", (Exception,), {})
    helpers.device_registry = dev_reg
    helpers.update_coordinator = upd

    ha.components = components
    ha.const = const
    ha.helpers = helpers
    for name, mod in [
        ("homeassistant.components", components),
        ("homeassistant.components.sensor", sensor),
        ("homeassistant.const", const),
        ("homeassistant.helpers", helpers),
        ("homeassistant.helpers.device_registry", dev_reg),
        ("homeassistant.helpers.update_coordinator", upd),
    ]:
        sys.modules[name] = mod


_install_ha_stubs()

# The sensor module imports .const and .coordinator from the package; provide a
# package shell so a relative import resolves without loading the coordinator's
# own heavy dependency chain.
_pkg = types.ModuleType("custom_components.homgar")
_pkg.__path__ = [str(ROOT / "custom_components" / "homgar")]
sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
sys.modules["custom_components.homgar"] = _pkg
_const = types.ModuleType("custom_components.homgar.const")
_const.DOMAIN = "homgar"
sys.modules["custom_components.homgar.const"] = _const
_coord = types.ModuleType("custom_components.homgar.coordinator")
_coord.HomGarCoordinator = object
sys.modules["custom_components.homgar.coordinator"] = _coord

_spec = importlib.util.spec_from_file_location(
    "custom_components.homgar.diagnostic_command_sensors",
    ROOT / "custom_components" / "homgar" / "diagnostic_command_sensors.py",
)
sensors_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = sensors_mod
_spec.loader.exec_module(sensors_mod)


class _FakeClient:
    def __init__(self):
        self.write_failure_count = 0
        self.last_write_failure_at = None
        self.last_write_failure_what = None
        self.last_write_failure_error = None


class _FakeCoordinator:
    def __init__(self, client):
        self._client = client


_HUB = {"mid": 12345}


# --- the sensors ------------------------------------------------------------


def _test_sensor_set():
    client = _FakeClient()
    coord = _FakeCoordinator(client)
    built = sensors_mod.build_command_diagnostic_sensors(coord, _HUB, "entry1")
    check("both command diagnostic sensors are built", len(built) == 2, f"got {len(built)}")
    uids = {s._attr_unique_id for s in built}
    check("unique ids are entry-scoped",
          uids == {"entry1_command_failure_count", "entry1_last_command_failure"}, f"got {uids}")
    check("both are DIAGNOSTIC (not cluttering the main device page)",
          all(s._attr_entity_category == "diagnostic" for s in built))
    check("both attach to the hub device",
          all(s.device_info["identifiers"] == {("homgar", "rainpoint_hub_12345")} for s in built))

    other = sensors_mod.build_command_diagnostic_sensors(coord, _HUB, "entry2")
    check("a second config entry gets its own unique ids",
          {s._attr_unique_id for s in other}.isdisjoint(uids))


def _test_sensors_read_live_client_state():
    """A failure between polls must be visible immediately, so the sensors must
    read the client rather than a coordinator snapshot."""
    client = _FakeClient()
    count, last = sensors_mod.build_command_diagnostic_sensors(
        _FakeCoordinator(client), _HUB, "entry1")

    check("count starts at zero", count.native_value == 0)
    check("last-failure timestamp starts empty", last.native_value is None)

    when = datetime(2026, 8, 22, 5, 2, 28, tzinfo=timezone.utc)
    client.write_failure_count = 3
    client.last_write_failure_at = when
    client.last_write_failure_what = "controlWorkMode"
    client.last_write_failure_error = "controlWorkMode: Connection timeout to host"

    check("count reflects the client without a coordinator refresh",
          count.native_value == 3, f"got {count.native_value}")
    check("timestamp reflects the client", last.native_value == when)
    attrs = last.extra_state_attributes
    check("the failing command is exposed as an attribute",
          attrs.get("command") == "controlWorkMode", f"got {attrs!r}")
    check("the error text is exposed as an attribute",
          "Connection timeout" in (attrs.get("last_error") or ""), f"got {attrs!r}")
    check("the count sensor is TOTAL_INCREASING (usable in statistics)",
          count._attr_state_class == "total_increasing")
    check("the timestamp sensor is a TIMESTAMP device class",
          last._attr_device_class == "timestamp")


# --- the notification wiring ------------------------------------------------


def _test_notification_wiring():
    """Exercises _wire_write_failure_notification from __init__.py without
    importing the whole integration, by executing just that function's source
    against a fake persistent_notification module."""
    created: list[dict] = []

    pn = types.ModuleType("homeassistant.components.persistent_notification")

    def _async_create(hass, message, title=None, notification_id=None):
        created.append({"message": message, "title": title, "id": notification_id})

    pn.async_create = _async_create
    sys.modules["homeassistant.components.persistent_notification"] = pn
    sys.modules["homeassistant.components"].persistent_notification = pn

    src = (ROOT / "custom_components" / "homgar" / "__init__.py").read_text()
    start = src.index("def _wire_write_failure_notification(")
    end = src.index("\nasync def async_setup_entry(", start)
    namespace: dict = {"HomeAssistant": object}
    exec(compile(src[start:end], "__init__.py", "exec"), namespace)
    wire = namespace["_wire_write_failure_notification"]

    class _Entry:
        entry_id = "abc123"
        title = "HomGar (test)"

    class _Client:
        on_write_failure = None

    client = _Client()
    wire(object(), client, _Entry())
    check("wiring attaches a callback to the client", callable(client.on_write_failure))

    client.on_write_failure("controlWorkMode", "Connection timeout to host")
    check("a failed command creates a notification", len(created) == 1, f"got {created!r}")
    note = created[0]
    check("the notification names the failing command",
          "controlWorkMode" in note["message"], note["message"])
    check("the notification says the device did not change state",
          "did not change state" in note["message"], note["message"])
    check("the notification points at the tracking issue",
          "issues/82" in note["message"], note["message"])
    check("the notification title identifies which account",
          "HomGar (test)" in (note["title"] or ""), str(note["title"]))
    check("the notification id is entry-scoped",
          note["id"] == "homgar_write_failed_abc123", str(note["id"]))

    # The whole point of a stable id: a brownout kills several commands in a row.
    for _ in range(5):
        client.on_write_failure("controlWorkMode", "Connection timeout to host")
    ids = {n["id"] for n in created}
    check("six failures produce ONE notification id, not six",
          len(ids) == 1, f"got {ids!r}")

    # A second config entry must still be able to alert independently.
    class _Entry2:
        entry_id = "def456"
        title = "HomGar (second account)"

    client2 = _Client()
    wire(object(), client2, _Entry2())
    client2.on_write_failure("setDeviceStatus", "boom")
    check("a second entry gets its own notification id",
          created[-1]["id"] == "homgar_write_failed_def456", str(created[-1]["id"]))


def main() -> int:
    print("Command-failure surface tests (issue #82)")
    _test_sensor_set()
    _test_sensors_read_live_client_state()
    _test_notification_wiring()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
