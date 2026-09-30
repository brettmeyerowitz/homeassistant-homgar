#!/usr/bin/env python3
"""Regenerate the README's supported-device list from the shipped catalogue.

That list is the first thing most readers look for — someone who found this on
HACS by searching "rainpoint" wants to know whether their model is in it. It
was maintained by hand, so it was correct only until the next catalogue
refresh; v3.1.0 adds 15 models and drops one.

Run this after refreshing the catalogue:

    python3 scripts/fetch-product-models.py
    python3 scripts/generate-supported-devices.py

`tests/run_readme_device_list_tests.py` fails if the two ever disagree, so the
list cannot go quietly stale again.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CATALOGUE = ROOT / "custom_components/homgar/data/product_models.json"

BEGIN = "<!-- BEGIN SUPPORTED MODELS -->"
END = "<!-- END SUPPORTED MODELS -->"
BLE_BEGIN = "<!-- BEGIN BLUETOOTH ONLY -->"
BLE_END = "<!-- END BLUETOOTH ONLY -->"


# Sensors that report only over Bluetooth, directly to the phone app. Their
# readings are cached on the phone and never reach RainPoint's servers, so the
# cloud answers with no status for them at all (an account containing one used
# to crash setup outright - see issue #97). A cloud integration cannot read
# them by any means, so listing them as supported sends people looking for a
# fault that is not theirs and cannot be fixed.
#
# Bluetooth *valves* are a different case and stay supported: those are still
# commanded through the cloud, which is what the DP control path exists for.
BLE_ONLY_MODEL_CODES = {283, 334, 381, 384}
BLE_ONLY_PRODUCT_CODES = {73, 74}


def _catalogue() -> list[dict]:
    return json.loads(CATALOGUE.read_text())["data"]["models"]


def _names_of(entry: dict) -> set[str]:
    names = {entry["model"]}
    dm = entry.get("displayModel", "")
    if dm:
        names.add(dm)
    return names


def ble_only_names() -> list[str]:
    """Names we must not advertise: Bluetooth-only sensors, plus their aliases."""
    names: set[str] = set()
    for m in _catalogue():
        if (
            m["modelCode"] in BLE_ONLY_MODEL_CODES
            or m["productCode"] in BLE_ONLY_PRODUCT_CODES
        ):
            names |= _names_of(m)
    return sorted(names)


def model_names() -> list[str]:
    """Every name the decoder answers to, including displayModel aliases."""
    excluded = set(ble_only_names())
    names: set[str] = set()
    for m in _catalogue():
        names |= _names_of(m)
    return sorted(names - excluded)


def main() -> int:
    names = model_names()
    text = README.read_text()

    if BEGIN not in text or END not in text:
        print(f"✗ {README} has no {BEGIN} / {END} markers", file=sys.stderr)
        return 1

    before, rest = text.split(BEGIN, 1)
    _, after = rest.split(END, 1)
    updated = before + BEGIN + "\n" + ", ".join(names) + "\n" + END + after

    excluded = ble_only_names()
    if BLE_BEGIN in updated and BLE_END in updated:
        b, r = updated.split(BLE_BEGIN, 1)
        _, a = r.split(BLE_END, 1)
        updated = b + BLE_BEGIN + "\n" + ", ".join(excluded) + "\n" + BLE_END + a

    updated, n = re.subn(
        r"\*\*\d+ models?\*\* are currently supported",
        f"**{len(names)} models** are currently supported",
        updated,
    )
    if n == 0:
        print("✗ could not find the model count sentence to update", file=sys.stderr)
        return 1

    if updated == text:
        print(f"✓ already up to date — {len(names)} models")
        return 0

    README.write_text(updated)
    print(f"✓ wrote {len(names)} models to {README.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
