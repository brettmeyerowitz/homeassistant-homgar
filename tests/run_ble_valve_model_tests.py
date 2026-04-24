"""Focused regression tests for BLE-backed valve model detection and DP payloads."""
from __future__ import annotations

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
            if (current / "custom_components" / "homgar" / "decoder.py").exists():
                return current
            if current.parent == current:
                break
            current = current.parent
    raise RuntimeError("Could not locate repository root containing custom_components/homgar")


ROOT = _find_repo_root()


def _load_decoder():
    path = ROOT / "custom_components" / "homgar" / "decoder.py"
    spec = importlib.util.spec_from_file_location("homgar_decoder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decoder = _load_decoder()


def _install_aiohttp_stub() -> None:
    if "aiohttp" in sys.modules:
        return
    aiohttp = types.ModuleType("aiohttp")

    class ClientSession:
        pass

    aiohttp.ClientSession = ClientSession
    sys.modules["aiohttp"] = aiohttp


def _load_client():
    _install_aiohttp_stub()
    path = ROOT / "custom_components" / "homgar" / "api" / "client.py"
    spec = importlib.util.spec_from_file_location("homgar_api_client", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


client_module = _load_client()

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
    print("\n🧪 BLE valve model regression tests")

    check(
        "HTV210B is detected as BLE-backed",
        decoder.uses_ble_valve_control("HTV210B") is True,
    )
    check(
        "HTV224B is detected as BLE-backed",
        decoder.uses_ble_valve_control("HTV224B") is True,
    )
    check(
        "HTV203FRF is not detected as BLE-backed",
        decoder.uses_ble_valve_control("HTV203FRF") is False,
    )
    check(
        "unknown models default to non-BLE control",
        decoder.uses_ble_valve_control("DOES_NOT_EXIST") is False,
    )
    client = object.__new__(client_module.HomGarClient)
    check(
        "BLE open encodes 10 minutes as little-endian hex",
        client._encode_control_work_mode_dp_param(1, 600) == "58020000",
    )
    check(
        "BLE stop encodes zero runtime blob",
        client._encode_control_work_mode_dp_param(0, 600) == "00000000",
    )
    check(
        "BLE open payload matches captured HTV210B app request",
        client._build_control_work_mode_dp_payload(
            mid=250714,
            addr=1,
            device_name="MAC-744DBD4A2A00",
            product_key="a3QrDxYPTM2",
            port=1,
            mode=1,
            duration=600,
        ) == {
            "mid": "250714",
            "productKey": "a3QrDxYPTM2",
            "deviceName": "MAC-744DBD4A2A00",
            "mode": 1,
            "addr": 1,
            "port": 1,
            "param": "58020000",
            "dpCode": 1,
        },
    )
    check(
        "BLE stop payload matches captured HTV210B app request",
        client._build_control_work_mode_dp_payload(
            mid=250714,
            addr=1,
            device_name="MAC-744DBD4A2A00",
            product_key="a3QrDxYPTM2",
            port=1,
            mode=0,
            duration=0,
        ) == {
            "mid": "250714",
            "productKey": "a3QrDxYPTM2",
            "deviceName": "MAC-744DBD4A2A00",
            "mode": 0,
            "addr": 1,
            "port": 1,
            "param": "00000000",
            "dpCode": 1,
        },
    )

    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"BLE valve model results: {PASS}/{total} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
