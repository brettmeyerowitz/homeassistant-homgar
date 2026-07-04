"""Regression tests for area seeding (issues #63 and #70).

`seed_device_areas` must:

- On a RELOAD (``is_first_setup=False``) never (re)create an area or assign a
  device to one. A user who deletes the HomGar-created "My Home" area finds their
  device's ``area_id`` nulled by HA; recreating it on the next reload is the #70
  bug. Reloads still backfill missing device name/model (the #63 behaviour).
- On FIRST setup (``is_first_setup=True``) create the per-home area and seed
  devices that have no area yet.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _find_repo_root() -> Path:
    # Candidates cover both host runs (repo checkout) and the ha-test container,
    # where the integration is deployed under /config.
    candidates = [Path(__file__).resolve().parent, Path.cwd(), Path("/config")]
    for start in candidates:
        current = start
        while True:
            if (current / "custom_components" / "homgar" / "areas.py").exists():
                return current
            if current.parent == current:
                break
            current = current.parent
    raise RuntimeError("Could not locate repository root containing custom_components/homgar")


ROOT = _find_repo_root()


def _load_module(module_name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# --- Stub the HA registry helpers that areas.py lazily imports ---------------
_ha = types.ModuleType("homeassistant")
_ha_helpers = types.ModuleType("homeassistant.helpers")
_ar_mod = types.ModuleType("homeassistant.helpers.area_registry")
_dr_mod = types.ModuleType("homeassistant.helpers.device_registry")

# The fakes are injected per-test via these module-level globals.
_ar_mod.async_get = lambda hass: hass["area_reg"]
_dr_mod.async_get = lambda hass: hass["device_reg"]

sys.modules["homeassistant"] = _ha
sys.modules["homeassistant.helpers"] = _ha_helpers
sys.modules["homeassistant.helpers.area_registry"] = _ar_mod
sys.modules["homeassistant.helpers.device_registry"] = _dr_mod

# Package scaffolding so areas.py's ``from .const import ...`` resolves.
sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
sys.modules.setdefault("custom_components.homgar", types.ModuleType("custom_components.homgar"))
_load_module("custom_components.homgar.const", "custom_components/homgar/const.py")
_load_module("custom_components.homgar.decoder", "custom_components/homgar/decoder.py")
areas = _load_module("custom_components.homgar.areas", "custom_components/homgar/areas.py")


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


# --- Fakes -------------------------------------------------------------------
class FakeArea:
    def __init__(self, area_id: str, name: str):
        self.id = area_id
        self.name = name


class FakeAreaRegistry:
    def __init__(self):
        self._by_name: dict[str, FakeArea] = {}
        self.created: list[str] = []

    def async_get_area_by_name(self, name):
        return self._by_name.get(name)

    def async_create(self, name):
        area = FakeArea(f"area_{name}", name)
        self._by_name[name] = area
        self.created.append(name)
        return area

    def seed_existing(self, name):
        self._by_name[name] = FakeArea(f"area_{name}", name)


class FakeDevice:
    def __init__(self, device_id, identifiers, area_id=None, name="", model=""):
        self.id = device_id
        self.identifiers = identifiers
        self.area_id = area_id
        self.name = name
        self.model = model


class FakeDeviceRegistry:
    def __init__(self, devices):
        self._devices = list(devices)
        self.updates: list[tuple[str, dict]] = []

    def async_get_device(self, identifiers):
        for d in self._devices:
            if d.identifiers == identifiers:
                return d
        return None

    def async_update_device(self, device_id, **kwargs):
        self.updates.append((device_id, kwargs))
        for d in self._devices:
            if d.id == device_id:
                for k, v in kwargs.items():
                    setattr(d, k, v)


class FakeEntry:
    def __init__(self, options=None):
        self.options = options or {}


class FakeCoordinator:
    def __init__(self, data):
        self.data = data


DOMAIN = "homgar"


def _hub_identifiers(mid):
    return {(DOMAIN, f"rainpoint_hub_{mid}")}


# --- Tests -------------------------------------------------------------------
def _test_reload_does_not_recreate_deleted_area():
    """#70: on reload, a hub whose area was deleted (area_id=None) is left alone."""
    area_reg = FakeAreaRegistry()  # user deleted "My Home" -> registry empty
    hub = FakeDevice("hub1", _hub_identifiers(10), area_id=None, name="Hub", model="HWG")
    device_reg = FakeDeviceRegistry([hub])
    hass = {"area_reg": area_reg, "device_reg": device_reg}
    coord = FakeCoordinator({"hubs": [{"mid": 10, "homeName": "My Home"}], "sensors": {}})

    areas.seed_device_areas(hass, FakeEntry(), coord, is_first_setup=False)

    check("reload does not create the deleted area", area_reg.created == [], str(area_reg.created))
    check("reload leaves hub area_id None", hub.area_id is None, f"area_id={hub.area_id}")


def _test_reload_still_backfills_name_and_model():
    """#63: name/model backfill keeps running on reload even though area work is gated."""
    area_reg = FakeAreaRegistry()
    hub = FakeDevice("hub1", _hub_identifiers(10), area_id=None, name="", model="")
    device_reg = FakeDeviceRegistry([hub])
    hass = {"area_reg": area_reg, "device_reg": device_reg}
    coord = FakeCoordinator(
        {"hubs": [{"mid": 10, "homeName": "My Home", "name": "My Hub", "model": "HWG0538WRF"}], "sensors": {}}
    )

    areas.seed_device_areas(hass, FakeEntry(), coord, is_first_setup=False)

    check("reload backfills hub name", hub.name == "My Hub", f"name={hub.name!r}")
    check("reload backfills hub model", hub.model == "HWG0538WRF", f"model={hub.model!r}")
    check("reload backfill still does not touch area", hub.area_id is None and area_reg.created == [])


def _test_first_setup_creates_and_assigns_area():
    """Fresh install seeds the per-home area and assigns the hub to it."""
    area_reg = FakeAreaRegistry()
    hub = FakeDevice("hub1", _hub_identifiers(10), area_id=None, name="Hub", model="HWG")
    device_reg = FakeDeviceRegistry([hub])
    hass = {"area_reg": area_reg, "device_reg": device_reg}
    coord = FakeCoordinator({"hubs": [{"mid": 10, "homeName": "My Home"}], "sensors": {}})

    areas.seed_device_areas(hass, FakeEntry(), coord, is_first_setup=True)

    check("first setup creates the area", area_reg.created == ["My Home"], str(area_reg.created))
    check("first setup assigns hub to area", hub.area_id == "area_My Home", f"area_id={hub.area_id}")


def _test_reload_does_not_assign_sensor_devices():
    """#70: on reload, sensor/controller devices with no area are not assigned."""
    area_reg = FakeAreaRegistry()
    sensor_dev = FakeDevice("s1", {(DOMAIN, "10_2")}, area_id=None, name="Valve", model="HTV0535FRF")
    device_reg = FakeDeviceRegistry([sensor_dev])
    hass = {"area_reg": area_reg, "device_reg": device_reg}
    coord = FakeCoordinator(
        {"hubs": [], "sensors": {"s": {"mid": 10, "addr": 2, "home_name": "My Home", "model": "HTV0535FRF"}}}
    )

    areas.seed_device_areas(hass, FakeEntry(), coord, is_first_setup=False)

    check("reload does not create area for sensors", area_reg.created == [], str(area_reg.created))
    check("reload leaves sensor area_id None", sensor_dev.area_id is None, f"area_id={sensor_dev.area_id}")


def main() -> int:
    print("Area seeding regression tests (#63, #70)")
    _test_reload_does_not_recreate_deleted_area()
    _test_reload_still_backfills_name_and_model()
    _test_first_setup_creates_and_assigns_area()
    _test_reload_does_not_assign_sensor_devices()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
