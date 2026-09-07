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


def catalogue_keys() -> set[str]:
    """Every name the decoder will answer to, aliases included."""
    data = json.loads((ROOT / "custom_components/homgar/data/product_models.json").read_text())
    keys: set[str] = set()
    for m in data["data"]["models"]:
        keys.add(m["model"])
        dm = m.get("displayModel", "")
        if dm:
            keys.add(dm)
    return keys


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

    m = re.search(r"\*\*(\d+) models?\*\* are currently supported", readme)
    check("the stated count is present and correct",
          m is not None and int(m.group(1)) == len(expected),
          f"README says {m.group(1) if m else 'nothing'}, catalogue has {len(expected)}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
