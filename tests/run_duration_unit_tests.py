#!/usr/bin/env python3
"""Regression tests for valve duration unit options."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
for candidate in (Path(__file__).resolve().parent, Path.cwd(), Path("/config")):
    current = candidate
    while True:
        if (current / "custom_components" / "homgar" / "number.py").exists():
            ROOT = current
            break
        if current.parent == current:
            break
        current = current.parent
    if (ROOT / "custom_components" / "homgar" / "number.py").exists():
        break
sys.path.insert(0, str(ROOT))

from custom_components.homgar import number  # noqa: E402
from custom_components.homgar.const import (  # noqa: E402
    CONF_VALVE_DURATION_UNIT,
    DEFAULT_VALVE_DURATION_UNIT,
    VALVE_DURATION_UNIT_MINUTES,
    VALVE_DURATION_UNIT_SECONDS,
)

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        print(f"  ✅ {name}")
        PASS += 1
    else:
        print(f"  ❌ {name}: {detail}")
        FAIL += 1


def fake_coordinator(options: dict | None = None):
    return SimpleNamespace(_entry=SimpleNamespace(options=options or {}))


def main() -> int:
    print("\n🧪 Valve duration unit regression tests")

    check(
        "default duration unit is minutes",
        number._duration_unit_from_options(fake_coordinator()) == DEFAULT_VALVE_DURATION_UNIT,
    )
    check(
        "seconds option is honored",
        number._duration_unit_from_options(
            fake_coordinator({CONF_VALVE_DURATION_UNIT: VALVE_DURATION_UNIT_SECONDS})
        ) == VALVE_DURATION_UNIT_SECONDS,
    )
    check(
        "invalid option falls back to minutes",
        number._duration_unit_from_options(
            fake_coordinator({CONF_VALVE_DURATION_UNIT: "hours"})
        ) == VALVE_DURATION_UNIT_MINUTES,
    )
    check(
        "10 native minutes converts to 600 seconds",
        number._duration_seconds_from_native(10, VALVE_DURATION_UNIT_MINUTES) == 600,
    )
    check(
        "30 native seconds stays 30 seconds",
        number._duration_seconds_from_native(30, VALVE_DURATION_UNIT_SECONDS) == 30,
    )
    check(
        "600 seconds renders as 10 minutes",
        number._duration_native_from_seconds(600, VALVE_DURATION_UNIT_MINUTES) == 10,
    )
    check(
        "30 seconds renders as 30 seconds",
        number._duration_native_from_seconds(30, VALVE_DURATION_UNIT_SECONDS) == 30,
    )
    check(
        "minutes mode clamps to one minute minimum",
        number._clamp_duration_seconds(30, VALVE_DURATION_UNIT_MINUTES) == 60,
    )
    check(
        "seconds mode allows one-second minimum",
        number._clamp_duration_seconds(0, VALVE_DURATION_UNIT_SECONDS) == 1,
    )
    check(
        "seconds mode clamps to one-hour maximum",
        number._clamp_duration_seconds(7200, VALVE_DURATION_UNIT_SECONDS) == 3600,
    )

    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"Valve duration unit results: {PASS}/{total} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
