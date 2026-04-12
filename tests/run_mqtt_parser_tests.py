"""Focused regression tests for MQTT param parsing."""
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
            if (current / "custom_components" / "homgar" / "mqtt_client.py").exists():
                return current
            if current.parent == current:
                break
            current = current.parent
    raise RuntimeError("Could not locate repository root containing custom_components/homgar")


ROOT = _find_repo_root()


def _load_module():
    path = ROOT / "custom_components" / "homgar" / "mqtt_client.py"
    spec = importlib.util.spec_from_file_location("homgar_mqtt_client", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load mqtt_client module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mqtt_client = _load_module()
extract_updates = mqtt_client._extract_device_updates

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
    print("\n🧪 MQTT parser regression tests")

    parsed = extract_updates('103491408512|{"D01":{"value":"10#ABC"},"D02":{"value":"10#DEF"}}|0|0')
    check("extracts object after scalar prefix", isinstance(parsed, dict), repr(parsed))
    check("parsed D01 present", parsed is not None and "D01" in parsed, repr(parsed))
    check("parsed D02 present", parsed is not None and "D02" in parsed, repr(parsed))

    parsed = extract_updates("|103491408512")
    check("ignores bare scalar with leading pipe", parsed is None, repr(parsed))

    parsed = extract_updates("103491408513")
    check("ignores bare scalar", parsed is None, repr(parsed))

    parsed = extract_updates('{"D04":{"value":"10#PAYLOAD"}}')
    check("parses plain object body", isinstance(parsed, dict), repr(parsed))
    check("plain object contains D04", parsed is not None and "D04" in parsed, repr(parsed))

    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"MQTT parser results: {PASS}/{total} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
