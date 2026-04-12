"""Fixture-driven payload regression tests.

This runner intentionally avoids pytest so it can run both on the host and in
the ha-test container with only the standard library available.
"""
from __future__ import annotations

import json
import importlib.util
import math
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    """Resolve the project root for both repo and copied temp-script runs."""
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
    """Load decoder.py directly to avoid importing HA-dependent package init."""
    decoder_path = ROOT / "custom_components" / "homgar" / "decoder.py"
    spec = importlib.util.spec_from_file_location("homgar_decoder", decoder_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load decoder module from {decoder_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decode_payload = _load_decoder().decode_payload

SCRIPT_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
FIXTURE_ROOT = SCRIPT_FIXTURE_ROOT if SCRIPT_FIXTURE_ROOT.exists() else ROOT / "tests" / "fixtures"
INDEX_FILE = FIXTURE_ROOT / "payload_index.json"

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


def get_path(data: dict, path: str):
    """Read a dotted path from a nested decode result."""
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def evaluate_expected(actual, expected) -> tuple[bool, str]:
    """Evaluate one expectation entry against an actual decoded value."""
    if isinstance(expected, dict):
        if expected.get("present") and actual is None:
            return False, "value missing"
        if "one_of" in expected and actual not in expected["one_of"]:
            return False, f"got {actual!r}"
        if "min" in expected:
            if actual is None or actual < expected["min"]:
                return False, f"got {actual!r}"
        if "max" in expected:
            if actual is None or actual > expected["max"]:
                return False, f"got {actual!r}"
        if "approx" in expected:
            tol = expected.get("tolerance", 0)
            if actual is None or not isinstance(actual, (int, float)):
                return False, f"got {actual!r}"
            if math.fabs(actual - expected["approx"]) > tol:
                return False, f"got {actual!r}"
        if "equal" in expected and actual != expected["equal"]:
            return False, f"got {actual!r}"
        return True, ""
    return (actual == expected, f"got {actual!r}")


def main() -> int:
    print("\n🧪 Fixture-driven payload corpus")
    index = json.loads(INDEX_FILE.read_text())
    for item in index["models"]:
        path = FIXTURE_ROOT / item["file"]
        fixture = json.loads(path.read_text())
        model = fixture["model"]
        print(f"\n📦 {model}")
        for sample in fixture["samples"]:
            sample_id = sample["id"]
            result = decode_payload(model, sample["payload"])
            check(f"{sample_id} decoded", "error" not in result, str(result))
            if "error" in result:
                continue
            for field_path, expectation in sample["expected"].items():
                actual = get_path(result, field_path)
                ok, detail = evaluate_expected(actual, expectation)
                check(f"{sample_id} -> {field_path}", ok, detail)

    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"Fixture corpus results: {PASS}/{total} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
