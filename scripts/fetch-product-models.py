#!/usr/bin/env python3
"""Refresh custom_components/homgar/data/product_models.json from the vendor.

Run by a maintainer, never at runtime: decoding stays offline and the catalogue
ships with the integration, so a user's Home Assistant never depends on the
vendor being reachable to decode a payload.

    python3 scripts/fetch-product-models.py            # write the file
    python3 scripts/fetch-product-models.py --dry-run  # report, change nothing

Why the bare endpoint and appCode 1:

  * ``/productModel`` (bare) returns the shape this file already uses.
    ``/productModel/json`` is what the app itself calls, but its dp entries drop
    dpLen/dpDataType/dpDef and nest a richer ``specs`` object instead, so it is
    NOT a drop-in — ``_build_dp_index`` cannot read it.
  * appCode selects the catalogue: 1 = HomGar, 2 = RainPoint. HomGar is a strict
    superset, so 1 is the right one to ship.

Neither the endpoint nor the catalogue needs authentication.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

URL = "https://region3.homgarus.com/app/common/core/productModel"
APP_CODE = "1"

# The vendor rejects unfamiliar clients with 403 — Python's default
# "Python-urllib/x.y" is blocked just as "HomeAssistant" is, which is why
# api/client.py pins the same app-style value on every request.
USER_AGENT = "okhttp/4.9.2"
TARGET = Path(__file__).resolve().parents[1] / "custom_components" / "homgar" / "data" / "product_models.json"

# A fetch that comes back far smaller than what we ship is more likely a vendor
# hiccup or a truncated response than a real cull, and silently overwriting the
# catalogue with it would break decoding for every model that vanished.
MIN_RETAINED_FRACTION = 0.9


def fetch() -> dict:
    req = urllib.request.Request(
        URL, headers={"appCode": APP_CODE, "User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def models_of(doc: dict) -> list[dict]:
    try:
        return doc["data"]["models"]
    except (KeyError, TypeError):
        raise SystemExit("✗ unexpected response shape: no data.models")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    remote = fetch()
    new = models_of(remote)
    if not new:
        raise SystemExit("✗ refusing to write: the fetched catalogue is empty")

    current = json.loads(TARGET.read_text()) if TARGET.exists() else {"data": {"models": [], "version": None}}
    old = models_of(current)

    old_names = {m["model"] for m in old}
    new_names = {m["model"] for m in new}

    if len(new_names) < len(old_names) * MIN_RETAINED_FRACTION:
        raise SystemExit(
            f"✗ refusing to write: {len(new_names)} models fetched vs {len(old_names)} shipped "
            "— that is a suspicious drop, not a refresh"
        )

    added = sorted(new_names - old_names)
    removed = sorted(old_names - new_names)

    print(f"version   {current['data'].get('version')} -> {remote['data'].get('version')}")
    print(f"models    {len(old_names)} unique ({len(old)} entries) -> {len(new_names)} unique ({len(new)} entries)")
    print(f"added     {len(added)}: {', '.join(added) if added else '(none)'}")
    print(f"removed   {len(removed)}: {', '.join(removed) if removed else '(none)'}")

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    TARGET.write_text(json.dumps(remote, indent=2, ensure_ascii=False) + "\n")
    print(f"\n✓ wrote {TARGET}")
    print("  Now run scripts/pre-commit-docker-test.sh — the corpus must decode unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
