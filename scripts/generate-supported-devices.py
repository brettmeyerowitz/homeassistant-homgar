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


def model_names() -> list[str]:
    """Every name the decoder answers to, including displayModel aliases."""
    data = json.loads(CATALOGUE.read_text())
    names: set[str] = set()
    for m in data["data"]["models"]:
        names.add(m["model"])
        dm = m.get("displayModel", "")
        if dm:
            names.add(dm)
    return sorted(names)


def main() -> int:
    names = model_names()
    text = README.read_text()

    if BEGIN not in text or END not in text:
        print(f"✗ {README} has no {BEGIN} / {END} markers", file=sys.stderr)
        return 1

    before, rest = text.split(BEGIN, 1)
    _, after = rest.split(END, 1)
    updated = before + BEGIN + "\n" + ", ".join(names) + "\n" + END + after

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
