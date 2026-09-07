#!/usr/bin/env python3
"""Regression tests: duplicate model names must not lose a device's zones.

Issue #108, reported by @geoffly. A Pihode HIC819W-6 six-zone controller was
discovered but produced no valve entities at all.

The vendor catalogue lists some models TWICE — once as a category 1 "main
device" row with portNumber 0 and a handful of dp definitions, and once as a
category 6 row carrying the real portNumber and the full dp set. The registry
was built with ``result[key] = m`` in list order, so the LAST entry silently
won. For seven models that is the empty one, and every zone disappeared.

The reporter's own payload is the fixture: it decodes to port_number 1 with the
empty entry and to six ports with the right one, so this asserts behaviour
against real hardware rather than a constructed example.
"""
import sys

sys.path.insert(0, "/config")

from custom_components.homgar.decoder import (  # noqa: E402
    decode_payload,
    get_model_info,
    get_valve_ports,
)

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


# Every model that loses its zones to the last-entry-wins collision, with the
# port count the catalogue actually describes.
AFFECTED = {
    "HIC1200W": 12,
    "HIC1208W": 8,
    "HIC819W-6": 6,
    "HIC819W-4": 4,
    "HIC1204W": 4,
    "HPS551WRF": 1,
    "HWS388WRF-V7": 1,
}

print("\n🧪 duplicate catalogue entries resolve to the row that describes the device")

for model, ports in sorted(AFFECTED.items()):
    info = get_model_info(model)
    check(
        f"{model} keeps its {ports} port(s)",
        info is not None and (info.get("portNumber") or 0) == ports,
        f"got portNumber={None if info is None else info.get('portNumber')}",
    )

print("\n🧪 issue #108 — the reporter's own HIC819W-6 payload")

# Straight from the diagnostics attached to the issue.
PAYLOAD = "10#108800AF00000000B700403F03D800F700000000F9FF00"

check(
    "get_valve_ports reports all six zones",
    get_valve_ports("HIC819W-6") == [1, 2, 3, 4, 5, 6],
    f"got {get_valve_ports('HIC819W-6')}",
)

decoded = decode_payload("HIC819W-6", PAYLOAD)
check(
    "the payload decodes to six ports, not one",
    decoded.get("port_number") == 6,
    f"got {decoded.get('port_number')}",
)
check(
    "a port block exists for every zone",
    all(f"port_{p}" in decoded for p in range(1, 7)),
    f"got {sorted(k for k in decoded if k.startswith('port_'))}",
)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
