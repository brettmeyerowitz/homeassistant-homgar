"""Regression tests: "no MQTT frame yet" is UNKNOWN, not UNAVAILABLE.

Reported by a user on issue #82 (2026-08-23) while field-testing v3.0.45-beta.1.
They tried to gate a valve OPEN on the device's MQTT diagnostic entity being
available, and deadlocked: after an integration reload the entity for an *idle*
device stays `unavailable` until that device emits its first frame, and an idle
valve emits nothing until it is commanded. The preflight check could therefore
never pass.

The bug is a conflation Home Assistant is explicit about:

  * ``unavailable`` — the integration cannot determine the state at all
    (device offline, connection lost).
  * ``unknown``     — the entity is fine, there is simply no value yet.

A healthy MQTT session where one device has not spoken is squarely the second.
Four entities reported the first.

The coordinator already knew better. ``_update_mqtt_diagnostics`` refreshes the
client's ``connected`` flag on *every* poll, independent of whether any frame
arrived, so the honest signal was available and unused.

After this change ``unavailable`` means the MQTT session is genuinely down —
which makes it worth gating on — and ``unknown`` means connected but not yet
heard from. Stdlib only.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _find_repo_root() -> Path:
    for start in (Path(__file__).resolve().parent, Path.cwd(), Path("/config")):
        current = start
        while True:
            if (current / "custom_components" / "homgar" / "hub_entities.py").exists():
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


def _install_ha_stubs() -> None:
    if "homeassistant.components.select" in sys.modules:
        return
    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    components = types.ModuleType("homeassistant.components")

    class _Enum(str):
        pass

    sensor = types.ModuleType("homeassistant.components.sensor")
    sensor.SensorEntity = type("SensorEntity", (), {})
    sensor.SensorDeviceClass = type(
        "SensorDeviceClass", (), {"TIMESTAMP": _Enum("timestamp"),
                                  "SIGNAL_STRENGTH": _Enum("signal_strength")})
    sensor.SensorStateClass = type(
        "SensorStateClass", (), {"TOTAL_INCREASING": _Enum("total_increasing")})

    switch = types.ModuleType("homeassistant.components.switch")
    switch.SwitchEntity = type("SwitchEntity", (), {})
    select = types.ModuleType("homeassistant.components.select")
    select.SelectEntity = type("SelectEntity", (), {})

    const = types.ModuleType("homeassistant.const")
    const.EntityCategory = type(
        "EntityCategory", (), {"DIAGNOSTIC": _Enum("diagnostic"), "CONFIG": _Enum("config")})

    helpers = types.ModuleType("homeassistant.helpers")
    dev_reg = types.ModuleType("homeassistant.helpers.device_registry")
    dev_reg.DeviceInfo = dict
    entity = types.ModuleType("homeassistant.helpers.entity")
    entity.Entity = type("Entity", (), {})
    upd = types.ModuleType("homeassistant.helpers.update_coordinator")

    class _CoordinatorEntity:
        def __init__(self, coordinator, *a, **kw):
            self.coordinator = coordinator

    upd.CoordinatorEntity = _CoordinatorEntity
    upd.DataUpdateCoordinator = object
    upd.UpdateFailed = type("UpdateFailed", (Exception,), {})

    components.sensor, components.switch, components.select = sensor, switch, select
    helpers.device_registry, helpers.entity, helpers.update_coordinator = dev_reg, entity, upd
    ha.components, ha.const, ha.helpers = components, const, helpers
    for name, mod in [
        ("homeassistant.components", components),
        ("homeassistant.components.sensor", sensor),
        ("homeassistant.components.switch", switch),
        ("homeassistant.components.select", select),
        ("homeassistant.const", const),
        ("homeassistant.helpers", helpers),
        ("homeassistant.helpers.device_registry", dev_reg),
        ("homeassistant.helpers.entity", entity),
        ("homeassistant.helpers.update_coordinator", upd),
    ]:
        sys.modules[name] = mod


_install_ha_stubs()

_pkg = types.ModuleType("custom_components.homgar")
_pkg.__path__ = [str(ROOT / "custom_components" / "homgar")]
sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
sys.modules["custom_components.homgar"] = _pkg
_const = types.ModuleType("custom_components.homgar.const")
_const.DOMAIN = "homgar"
sys.modules["custom_components.homgar.const"] = _const
_coord_stub = types.ModuleType("custom_components.homgar.coordinator")
_coord_stub.HomGarCoordinator = object
sys.modules["custom_components.homgar.coordinator"] = _coord_stub


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


hub_mod = _load("custom_components.homgar.hub_entities",
                "custom_components/homgar/hub_entities.py")
diag_mod = _load("custom_components.homgar.diagnostic_sensors",
                 "custom_components/homgar/diagnostic_sensors.py")


class _Coordinator:
    """Mirrors the real coordinator's contract: _mqtt_diagnostics plus the
    mqtt_connected property the entities are supposed to consult."""

    def __init__(self, diagnostics=None):
        self._mqtt_diagnostics = diagnostics if diagnostics is not None else {}
        self.data = {"sensors": {}}

    @property
    def mqtt_connected(self) -> bool:
        return any(bool(d.get("connected")) for d in self._mqtt_diagnostics.values())


_HUB = {"mid": 777, "name": "Hub"}
_HUB_KEY = "rainpoint_hub_777"
_SUB_KEY = "777_3"
_SUB_INFO = {"mid": 777, "addr": 3, "sub_name": "Zone 1", "model": "HTV113FRF"}


def _hub_sensors(coord):
    return [hub_mod.HomGarHubMqttRawPayloadSensor(coord, _HUB),
            hub_mod.HomGarHubMqttFriendlySensor(coord, _HUB)]


def _sub_sensors(coord):
    return [diag_mod.HomGarMqttRawPayloadSensor(coord, _SUB_KEY, _SUB_INFO, "zone1"),
            diag_mod.HomGarMqttFriendlySensor(coord, _SUB_KEY, _SUB_INFO, "zone1")]


# --- the coordinator's own signal -------------------------------------------


def _load_real_coordinator():
    """Load the real coordinator module so mqtt_connected is exercised for real.

    The first version of this suite asserted the property existed by grepping
    the source, and stubbed the property itself in the fake coordinator below.
    That is how the post-reload bug got through: the entities were tested, the
    thing they depend on never was.
    """
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = type("HomeAssistant", (), {})
    pn = types.ModuleType("homeassistant.components.persistent_notification")
    pn.async_create = lambda *a, **kw: None
    aio = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aio.async_get_clientsession = lambda *a, **kw: None
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.components.persistent_notification"] = pn
    sys.modules["homeassistant.helpers.aiohttp_client"] = aio
    sys.modules["homeassistant.components"].persistent_notification = pn

    api = types.ModuleType("custom_components.homgar.api")
    api.HomGarClient = type("HomGarClient", (), {})
    api.HomGarApiError = type("HomGarApiError", (Exception,), {})
    dec = types.ModuleType("custom_components.homgar.decoder")
    dec.decode_payload = lambda *a, **kw: {}
    dec.get_switch_ports = lambda *a, **kw: []
    dec.get_valve_ports = lambda *a, **kw: []
    tel = types.ModuleType("custom_components.homgar.telemetry")
    async def _noop(*a, **kw):
        return None
    tel.async_maybe_ping = _noop
    for name, mod in [("custom_components.homgar.api", api),
                      ("custom_components.homgar.decoder", dec),
                      ("custom_components.homgar.telemetry", tel)]:
        sys.modules[name] = mod

    # The real const module — the coordinator imports many names from it.
    del sys.modules["custom_components.homgar.const"]
    _load("custom_components.homgar.const", "custom_components/homgar/const.py")
    return _load("custom_components.homgar.coordinator",
                 "custom_components/homgar/coordinator.py")


class _FakeMqttClient:
    def __init__(self, connected):
        self.connected = connected


class _LegacyMqttClient:
    """No `connected` property — only get_diagnostics()."""

    def __init__(self, connected, raises=False):
        self._connected = connected
        self._raises = raises

    def get_diagnostics(self):
        if self._raises:
            raise RuntimeError("diagnostics exploded")
        return {"connected": self._connected}


class _Hass:
    def __init__(self, data):
        self.data = data


class _Entry:
    entry_id = "entry1"


def _real_coord(mqtt_client=None, include_entry=True, include_domain=True,
                diagnostics=None):
    mod = _REAL_COORD
    coord = mod.HomGarCoordinator.__new__(mod.HomGarCoordinator)
    entry_data = {} if mqtt_client is None else {"mqtt_client": mqtt_client}
    domain_data = {"entry1": entry_data} if include_entry else {}
    coord.hass = _Hass({"homgar": domain_data} if include_domain else {})
    coord._entry = _Entry()
    coord._mqtt_diagnostics = diagnostics if diagnostics is not None else {}
    return coord


def _test_coordinator_mqtt_connected():
    check("the coordinator exposes mqtt_connected as a property",
          isinstance(getattr(_REAL_COORD.HomGarCoordinator, "mqtt_connected", None),
                     property))

    # THE REGRESSION. async_setup_entry runs the coordinator's first refresh
    # before it creates the MQTT client, so right after a reload the per-poll
    # diagnostics cache is empty. Reading the cache reported "not connected" for
    # a whole poll interval — the exact window where an automation gates a
    # command on an idle device.
    coord = _real_coord(_FakeMqttClient(True), diagnostics={})
    check("connected is reported from the live client even with an empty cache",
          coord.mqtt_connected is True,
          "post-reload window: this is the bug that shipped in the first attempt")

    coord = _real_coord(_FakeMqttClient(False), diagnostics={})
    check("a disconnected client reports not connected", coord.mqtt_connected is False)

    check("no client yet means not connected",
          _real_coord(None).mqtt_connected is False)
    check("a missing entry means not connected",
          _real_coord(_FakeMqttClient(True), include_entry=False).mqtt_connected is False)
    check("a missing domain means not connected",
          _real_coord(_FakeMqttClient(True), include_domain=False).mqtt_connected is False)

    # A stale cache must not be able to override the live client either way.
    stale = {"rainpoint_hub_777": {"connected": True}}
    check("a stale cache saying connected cannot override a down client",
          _real_coord(_FakeMqttClient(False), diagnostics=stale).mqtt_connected is False)

    check("falls back to get_diagnostics for a client without the property",
          _real_coord(_LegacyMqttClient(True)).mqtt_connected is True)
    check("availability never raises, even if diagnostics does",
          _real_coord(_LegacyMqttClient(True, raises=True)).mqtt_connected is False)


# --- the deadlock itself ----------------------------------------------------


def _test_idle_device_is_unknown_not_unavailable():
    """The reported deadlock: MQTT up, this device has never spoken."""
    coord = _Coordinator({_HUB_KEY: {"connected": True, "messages_received": 12}})

    for s in _hub_sensors(coord):
        check(f"hub {type(s).__name__}: available while MQTT is up",
              s.available is True)
        check(f"hub {type(s).__name__}: value is unknown, not a fake value",
              s.native_value is None, f"got {s.native_value!r}")

    # The sub-device key does not exist at all until its first frame — this is
    # the exact case that could never resolve for an idle valve.
    check("the idle sub-device has no diagnostics entry yet",
          _SUB_KEY not in coord._mqtt_diagnostics)
    for s in _sub_sensors(coord):
        check(f"sub-device {type(s).__name__}: available while MQTT is up",
              s.available is True,
              "an idle valve never emits until commanded, so gating a command "
              "on this deadlocks")
        check(f"sub-device {type(s).__name__}: value is unknown",
              s.native_value is None, f"got {s.native_value!r}")


def _test_unavailable_still_means_something():
    """If availability were hard-coded True the entity would be useless as a
    preflight gate. MQTT genuinely down must still read unavailable."""
    coord = _Coordinator({_HUB_KEY: {"connected": False}})
    for s in _hub_sensors(coord) + _sub_sensors(coord):
        check(f"{type(s).__name__}: unavailable when MQTT is down",
              s.available is False)

    empty = _Coordinator({})
    for s in _hub_sensors(empty) + _sub_sensors(empty):
        check(f"{type(s).__name__}: unavailable before any diagnostics exist",
              s.available is False)


def _test_values_appear_once_a_frame_arrives():
    coord = _Coordinator({
        _HUB_KEY: {"connected": True, "raw_payload": {"a": 1},
                   "friendly_summary": "hub said hello",
                   "last_received": "2026-08-24T05:00:00+00:00"},
        _SUB_KEY: {"connected": True, "raw_payload": {"b": 2},
                   "friendly_summary": "zone 1 closed",
                   "last_received": "2026-08-24T05:00:01+00:00"},
    })
    raw_hub, friendly_hub = _hub_sensors(coord)
    raw_sub, friendly_sub = _sub_sensors(coord)
    check("hub raw payload appears after a frame", raw_hub.native_value is not None)
    check("hub summary appears after a frame",
          friendly_hub.native_value == "hub said hello", str(friendly_hub.native_value))
    check("sub-device raw payload appears after a frame", raw_sub.native_value is not None)
    check("sub-device summary appears after a frame",
          friendly_sub.native_value == "zone 1 closed", str(friendly_sub.native_value))
    check("last_received is exposed so an automation can check freshness",
          raw_sub.extra_state_attributes.get("last_received") is not None)
    for s in (raw_hub, friendly_hub, raw_sub, friendly_sub):
        check(f"{type(s).__name__}: still available with data", s.available is True)


def _test_one_device_silent_does_not_hide_another():
    """A frame from the hub must not make a silent valve look like it reported,
    and a silent valve must not drag the hub's entity down."""
    coord = _Coordinator({
        _HUB_KEY: {"connected": True, "raw_payload": {"a": 1},
                   "friendly_summary": "hub said hello"},
    })
    raw_hub, _ = _hub_sensors(coord)
    raw_sub, _ = _sub_sensors(coord)
    check("the hub reports its payload", raw_hub.native_value is not None)
    check("the silent valve is available but valueless",
          raw_sub.available is True and raw_sub.native_value is None,
          f"available={raw_sub.available} value={raw_sub.native_value!r}")


_REAL_COORD = _load_real_coordinator()


def main() -> int:
    print("MQTT availability semantics tests (issue #82 follow-up)")
    _test_coordinator_mqtt_connected()
    _test_idle_device_is_unknown_not_unavailable()
    _test_unavailable_still_means_something()
    _test_values_appear_once_a_frame_arrives()
    _test_one_device_silent_does_not_hide_another()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
