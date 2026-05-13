"""Focused regression tests for MQTT param parsing."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


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
extract_hub_mid_candidates = mqtt_client._extract_hub_mid_candidates
looks_like_device_payload = mqtt_client._looks_like_device_payload

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


def collect_mqtt_callbacks(param: str) -> list[dict]:
    """Run _on_message without opening a real MQTT connection."""
    callbacks: list[dict] = []
    client = mqtt_client.HomGarMQTTClient.__new__(mqtt_client.HomGarMQTTClient)
    client._messages_received = 0
    client._last_message_time = None
    client._on_message_callback = callbacks.append
    payload = json.dumps({"params": {"param": param}}).encode()
    msg = SimpleNamespace(topic="test/topic", payload=payload)
    client._on_message(None, None, msg)
    return callbacks


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

    parsed = extract_updates("1|1776014190215|103441486619")
    check("ignores scalar triplet fragment", parsed is None, repr(parsed))

    parsed = extract_updates('{"D04":{"value":"10#PAYLOAD"}}')
    check("parses plain object body", isinstance(parsed, dict), repr(parsed))
    check("plain object contains D04", parsed is not None and "D04" in parsed, repr(parsed))

    check("accepts tlv device payload", looks_like_device_payload("10#108800AF00000000"), "expected True")
    check(
        "accepts legacy ascii valve payload",
        looks_like_device_payload("1,-71,1;0,0,0,0,0,0|32,0,0,0,600,0"),
        "expected True",
    )
    check(
        "rejects scalar mqtt fragment",
        not looks_like_device_payload("1|1776014190215|103441486619"),
        "expected False",
    )
    check("rejects hub RSSI state", not looks_like_device_payload("0,-68"), "expected False")

    last6, candidates = extract_hub_mid_candidates("P260412163703000017280081139929")
    check("mid extraction keeps raw candidate", last6 == "139929", repr((last6, candidates)))
    check("mid extraction includes raw mid", candidates and candidates[0] == "139929", repr(candidates))
    check("mid extraction includes stripped-leading-1 alias", "39929" in candidates, repr(candidates))

    callbacks = collect_mqtt_callbacks(
        '#P260513201756000017870151267334|{"state":{"time":1778701510269,'
        '"value":"10#DC0103E1C900D82020B778445B19AF00000000"}}|0|0#'
    )
    check("emits MQTT callback for state device payload", len(callbacks) == 1, repr(callbacks))
    check("preserves state device key", callbacks and callbacks[0]["device_key"] == "state", repr(callbacks))
    check("preserves state raw payload", callbacks and callbacks[0]["payload"].startswith("10#DC01"), repr(callbacks))

    callbacks = collect_mqtt_callbacks(
        '#P260513201756000017870151267334|{"state":{"time":1778701510269,"value":"0,-68"}}|0|0#'
    )
    check("ignores MQTT RSSI-only state", callbacks == [], repr(callbacks))

    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"MQTT parser results: {PASS}/{total} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
