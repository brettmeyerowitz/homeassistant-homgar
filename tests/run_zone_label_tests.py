"""Focused regression tests for per-port friendly labels from portDescribe."""
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
    print("\n🧪 Zone label regression tests")

    timer = {"port_describe": "Outdoor Supply Line|Garage Hose"}
    check(
        "parses both port labels",
        const.get_port_labels(timer) == ["Outdoor Supply Line", "Garage Hose"],
        repr(const.get_port_labels(timer)),
    )
    check(
        "formats valve name from portDescribe",
        const.format_port_entity_name("Garage Water Timer", timer, 2) == "Garage Water Timer Garage Hose",
        const.format_port_entity_name("Garage Water Timer", timer, 2),
    )
    check(
        "formats duration name from portDescribe",
        const.format_port_entity_name("Garage Water Timer", timer, 1, "Duration")
        == "Garage Water Timer Outdoor Supply Line Duration",
        const.format_port_entity_name("Garage Water Timer", timer, 1, "Duration"),
    )

    fallback = {}
    check(
        "falls back to Zone numbering when labels are absent",
        const.format_port_entity_name("Outdoor Water Timer", fallback, 2, "Last Session Volume")
        == "Outdoor Water Timer Zone 2 Last Session Volume",
        const.format_port_entity_name("Outdoor Water Timer", fallback, 2, "Last Session Volume"),
    )

    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"Zone label results: {PASS}/{total} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
