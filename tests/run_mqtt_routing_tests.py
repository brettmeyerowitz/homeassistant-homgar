"""Focused regression tests for coordinator MQTT routing."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path


def _find_repo_root() -> Path:
    candidates = [
        Path(__file__).resolve().parent,
        Path.cwd(),
        Path("/config"),
    ]
    for start in candidates:
        current = start
        while True:
            if (current / "custom_components" / "homgar" / "coordinator_mqtt.py").exists():
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


sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
sys.modules.setdefault("custom_components.homgar", types.ModuleType("custom_components.homgar"))

_load_module("custom_components.homgar.decoder", "custom_components/homgar/decoder.py")
coordinator_mqtt = _load_module(
    "custom_components.homgar.coordinator_mqtt",
    "custom_components/homgar/coordinator_mqtt.py",
)

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


class FakeCoordinator:
    def __init__(self):
        self.data = {
            "hubs": [
                {
                    "mid": 39929,
                    "hid": 1,
                    "name": "Front Yard Hub",
                    "model": "HIC801W",
                    "softVer": "1.0.0",
                    "subDevices": [],
                }
            ],
            "sensors": {
                "39929_0": {
                    "hid": 1,
                    "mid": 39929,
                    "addr": 0,
                    "home_name": "Home",
                    "hub_name": "Front Yard Hub",
                    "sub_name": "Front Yard Hub",
                    "model": "HIC801W",
                    "firmware_version": "1.0.0",
                    "raw_status": {"value": "10#108800AF00000000B700204200D800F700000000F9FF00"},
                    "data": {},
                    "type_flag": 0,
                }
            },
        }
        self._last_good_data = {}
        self._mqtt_diagnostics = {}
        self.updated = False

    def async_set_updated_data(self, data):
        self.updated = True
        self.data = data


async def _run_case() -> tuple[bool, dict, dict]:
    coordinator = FakeCoordinator()
    await coordinator_mqtt.handle_mqtt_update(
        coordinator,
        {
            "hub_mid": "139929",
            "hub_mid_candidates": ["139929", "39929"],
            "device_key": "D00",
            "payload": "10#108800AF00000000B700204200D800F700000000F9FF00",
        },
    )
    sensor = coordinator.data["sensors"]["39929_0"]
    diag = coordinator._mqtt_diagnostics.get("39929_0", {})
    return coordinator.updated, sensor, diag


def main() -> int:
    print("\n🧪 MQTT routing regression tests")
    updated, sensor, diag = asyncio.run(_run_case())
    check("routes D00 update using MID candidate alias", updated)
    check("updates hub-as-device sensor key", sensor["raw_status"]["value"].startswith("10#1088"), repr(sensor))
    check("decoded idle zone 1 state", sensor["data"].get("port_1", {}).get("is_watering") is False, repr(sensor["data"]))
    check("records mqtt diagnostics", bool(diag), repr(diag))

    hic = FakeCoordinator()
    hic.data = {
        "hubs": [
            {
                "mid": 240341,
                "hid": 55344,
                "name": "8 Zone Wifi Irrigation Controller",
                "model": "HIC801W",
                "softVer": "1.1.1026",
                "subDevices": [
                    {
                        "addr": 1,
                        "name": "8 Zone Wifi Irrigation Controller",
                        "model": "HIC801W",
                    }
                ],
            }
        ],
        "sensors": {
            "240341_1": {
                "hid": 55344,
                "mid": 240341,
                "addr": 1,
                "home_name": "Bushwillow",
                "hub_name": "8 Zone Wifi Irrigation Controller",
                "sub_name": "8 Zone Wifi Irrigation Controller",
                "model": "HIC801W",
                "firmware_version": "7",
                "raw_status": {"value": "10#108800AF00000000B700204200D800F700000000F9FF00"},
                "data": {},
                "type_flag": 1,
            }
        },
    }
    asyncio.run(
        coordinator_mqtt.handle_mqtt_update(
            hic,
            {
                "hub_mid": "240341",
                "hub_mid_candidates": ["240341"],
                "device_key": "D01",
                "payload": "10#108800AF68010000B7EC421919D821F703FF0300F9FF00",
            },
        )
    )
    hic_diag = hic._mqtt_diagnostics.get("240341_1", {})
    hic_data = hic.data["sensors"]["240341_1"]["data"]
    check("routes HIC801W D01 update", hic.updated, repr(hic.data["sensors"]["240341_1"]))
    check("decodes HIC801W active zone 3", hic_data.get("port_3", {}).get("is_watering") is True, repr(hic_data))
    check("marks other HIC801W zones idle", hic_data.get("port_2", {}).get("is_watering") is False, repr(hic_data))
    check(
        "summarizes HIC801W active zone in mqtt diagnostics",
        "zone 3: irrigation" in hic_diag.get("friendly_summary", ""),
        repr(hic_diag),
    )

    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"MQTT routing results: {PASS}/{total} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
