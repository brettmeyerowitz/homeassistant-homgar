#!/usr/bin/env python3
"""Regression tests: the secondary RSSI slot must survive the catalogue rename.

The vendor renamed the dp identity ``STA_RSSI2`` to ``STA_RSRP``. ``_dec_rssi``
looks the secondary slot up by identity, so refreshing product_models.json
would make that lookup match nothing — signal strength would quietly stop being
published for any device that reports on the secondary slot, with no error.

Scope, stated honestly: no payload in the corpus exercises this path. All 73
samples resolve RSSI from the primary ``STA_RSSI`` slot, so swapping catalogues
changes none of their decoded output. These tests are therefore synthetic by
necessity — they lock the fallback's behaviour rather than demonstrate a bug
observed in the field. See docs and [[v4-catalogue-refresh-plan]].
"""

from __future__ import annotations

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
sys.path.insert(0, str(ROOT))

# decoder.py imports nothing outside the standard library, but the package
# __init__ pulls in aiohttp and homeassistant. Loading the module by path keeps
# these tests runnable outside the ha-test container as well as inside it.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "homgar_decoder", ROOT / "custom_components" / "homgar" / "decoder.py"
)
_decoder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_decoder)
_dec_rssi = _decoder._dec_rssi

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


def slot(identity, raw):
    """One decoded entry occupying a single dp slot, plus its dp_index."""
    entries = [{"dp_id": 151, "name": identity, "type_value": bytes([0x00, raw])}]
    dp_index = {151: {"identity": identity, "dpPort": 0}}
    return entries, dp_index


print("\n🧪 secondary RSSI slot — both the old and the new identity")

# -62 dBm: 0xC2 is 194, which is above 127, so it reads as 194 - 256.
check(
    "the pre-rename identity STA_RSSI2 still resolves",
    _dec_rssi(*slot("STA_RSSI2", 0xC2)) == -62,
    f"got {_dec_rssi(*slot('STA_RSSI2', 0xC2))}",
)

check(
    "the post-rename identity STA_RSRP resolves",
    _dec_rssi(*slot("STA_RSRP", 0xC2)) == -62,
    f"got {_dec_rssi(*slot('STA_RSRP', 0xC2))}",
)

# The primary slot must still win when it holds a usable reading, so the
# fallback cannot mask a real primary value.
entries = [
    {"dp_id": 150, "name": "STA_RSSI", "type_value": bytes([0x00, 0xB5])},   # -75
    {"dp_id": 151, "name": "STA_RSRP", "type_value": bytes([0x00, 0xC2])},   # -62
]
dp_index = {
    150: {"identity": "STA_RSSI", "dpPort": 0},
    151: {"identity": "STA_RSRP", "dpPort": 0},
}
check(
    "the primary slot still takes precedence over the fallback",
    _dec_rssi(entries, dp_index) == -75,
    f"got {_dec_rssi(entries, dp_index)}",
)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
