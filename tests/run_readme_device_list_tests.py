#!/usr/bin/env python3
"""Regression tests: the README's supported-device list matches the catalogue.

The list is 100+ SKUs that a reader searches with Ctrl+F to answer the only
question that brings most people to this repo — "does it support my device?".
It was maintained by hand, which means it is correct exactly until the next
catalogue refresh and silently wrong afterwards.

v3.1.0 is that refresh: it adds 15 models and drops one, so the hand-written
list would have shipped stale. This test makes that a failure rather than a
thing someone notices months later.

Regenerate with: python3 scripts/generate-supported-devices.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (Path(__file__).resolve().parent, Path.cwd(), Path("/config")):
    current = candidate
    while True:
        if (current / "custom_components" / "homgar" / "decoder.py").exists():
            ROOT = current
            break
        if current.parent == current:
            break
        current = current.parent
    if (ROOT / "custom_components" / "homgar" / "decoder.py").exists():
        break

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


BEGIN = "<!-- BEGIN SUPPORTED MODELS -->"
END = "<!-- END SUPPORTED MODELS -->"
BLE_BEGIN = "<!-- BEGIN BLUETOOTH ONLY -->"
BLE_END = "<!-- END BLUETOOTH ONLY -->"

# The exclusion rule lives with the generator so the two cannot drift apart.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "gen_supported", ROOT / "scripts" / "generate-supported-devices.py"
)
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)


def catalogue_keys() -> set[str]:
    """Every name the decoder will answer to, aliases included."""
    data = json.loads((ROOT / "custom_components/homgar/data/product_models.json").read_text())
    keys: set[str] = set()
    for m in data["data"]["models"]:
        keys.add(m["model"])
        dm = m.get("displayModel", "")
        if dm:
            keys.add(dm)
    return keys - set(_gen.ble_only_names())


readme = (ROOT / "README.md").read_text()

print("\n🧪 README supported-device list")

check("the list is delimited by generator markers", BEGIN in readme and END in readme,
      "run scripts/generate-supported-devices.py")

if BEGIN in readme and END in readme:
    block = readme.split(BEGIN, 1)[1].split(END, 1)[0]
    listed = {m.strip() for m in re.split(r"[,\n]", block) if m.strip() and not m.startswith("`")}
    listed = {m.strip("`") for m in listed}
    expected = catalogue_keys()

    check("no model is missing from the README", not (expected - listed),
          f"missing: {sorted(expected - listed)}")
    check("the README lists nothing the catalogue does not have", not (listed - expected),
          f"stale: {sorted(listed - expected)}")

    # A Bluetooth-only sensor must be named somewhere, so that someone
    # searching for their model finds an answer instead of silence.
    check("the Bluetooth-only block is present", BLE_BEGIN in readme and BLE_END in readme,
          "run scripts/generate-supported-devices.py")
    if BLE_BEGIN in readme and BLE_END in readme:
        ble_block = readme.split(BLE_BEGIN, 1)[1].split(BLE_END, 1)[0]
        ble_listed = {x.strip() for x in re.split(r"[,\n]", ble_block) if x.strip()}
        ble_expected = set(_gen.ble_only_names())
        check("the Bluetooth-only list matches the catalogue rule",
              ble_listed == ble_expected,
              f"missing: {sorted(ble_expected - ble_listed)} stale: {sorted(ble_listed - ble_expected)}")
        check("no model is both supported and Bluetooth-only",
              not (listed & ble_expected),
              f"in both: {sorted(listed & ble_expected)}")

    m = re.search(r"\*\*(\d+) models?\*\* are currently supported", readme)
    check("the stated count is present and correct",
          m is not None and int(m.group(1)) == len(expected),
          f"README says {m.group(1) if m else 'nothing'}, catalogue has {len(expected)}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
