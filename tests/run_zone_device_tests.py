"""Focused regression tests for per-zone HA device helpers."""
from __future__ import annotations

import importlib.util
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
            if (current / "custom_components" / "homgar" / "const.py").exists():
                return current
            if current.parent == current:
                break
            current = current.parent
    raise RuntimeError("Could not locate repository root containing custom_components/homgar")


ROOT = _find_repo_root()


def _load_const_module():
    path = ROOT / "custom_components" / "homgar" / "const.py"
    spec = importlib.util.spec_from_file_location("homgar_const", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


const = _load_const_module()

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


def main() -> int:
    print("\n🧪 Zone device regression tests")

    timer = {"port_describe": "Outdoor Supply Line|Garage Hose"}
    check(
        "formats zone device name from portDescribe",
        const.format_port_device_name("Garage Water Timer", timer, 2) == "Garage Water Timer - Garage Hose",
        const.format_port_device_name("Garage Water Timer", timer, 2),
    )
    check(
        "matches grouped entity prefix to device name",
        const.format_port_entity_name(
            "Garage Water Timer",
            timer,
            2,
            "Cycle Type",
            use_device_prefix=True,
        ) == "Garage Water Timer - Garage Hose Cycle Type",
        const.format_port_entity_name(
            "Garage Water Timer",
            timer,
            2,
            "Cycle Type",
            use_device_prefix=True,
        ),
    )
    check(
        "supports grouped valve label suffix",
        const.format_port_entity_name(
            "Garage Water Timer",
            timer,
            2,
            "Valve",
            use_device_prefix=True,
        ) == "Garage Water Timer - Garage Hose Valve",
        const.format_port_entity_name(
            "Garage Water Timer",
            timer,
            2,
            "Valve",
            use_device_prefix=True,
        ),
    )
    check(
        "falls back to Zone numbering in device names",
        const.format_port_device_name("Outdoor Water Timer", {}, 1) == "Outdoor Water Timer - Zone 1",
        const.format_port_device_name("Outdoor Water Timer", {}, 1),
    )
    check(
        "builds stable zone device identifier",
        const.zone_device_identifier(139929, 3, 2) == "139929_3_zone2",
        const.zone_device_identifier(139929, 3, 2),
    )
    check(
        "keeps sub-device parent identifier for valve hubs",
        const.controller_device_identifier({"mid": 139929, "addr": 3, "type_flag": 0}) == "139929_3",
        const.controller_device_identifier({"mid": 139929, "addr": 3, "type_flag": 0}),
    )
    check(
        "uses hub parent identifier for wifi controllers",
        const.controller_device_identifier({"mid": 235522, "addr": 1, "type_flag": 1}) == "rainpoint_hub_235522",
        const.controller_device_identifier({"mid": 235522, "addr": 1, "type_flag": 1}),
    )

    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"Zone device results: {PASS}/{total} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
