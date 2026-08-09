"""ppm unit-constant tests (issue #84). Runs in the ha-test container against
the deployed integration at /config (imports Home Assistant).

HA 2026.7 added UnitOfRatio; 2026.8 then deprecated
CONCENTRATION_PARTS_PER_MILLION (removal in Core 2027.8). Cores at or below
2026.6 do not ship UnitOfRatio at all, so sensor_defs.py imports the enum when
present and falls back to the legacy constant otherwise. These tests pin both
branches so neither regresses.
"""
import enum
import importlib
import sys
import warnings

sys.path.insert(0, "/config")

import homeassistant.const as ha_const  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


def reload_sensor_defs():
    """Re-import sensor_defs so its module-level try/except runs again."""
    sys.modules.pop("custom_components.homgar.sensor_defs", None)
    return importlib.import_module("custom_components.homgar.sensor_defs")


class _FakeUnitOfRatio(enum.StrEnum):
    """Stand-in for HA 2026.7+ UnitOfRatio, so the modern branch is testable
    on any core version."""

    PARTS_PER_MILLION = "ppm"
    PARTS_PER_BILLION = "ppb"
    PERCENTAGE = "%"


print(f"HA {ha_const.__version__} (native UnitOfRatio: {hasattr(ha_const, 'UnitOfRatio')})")

# ── As deployed on this core ───────────────────────────────────────────────
print("\nAs deployed on this core:")
sd = reload_sensor_defs()
check("module imports without error", sd is not None)
check("PPM resolves to 'ppm'", sd.PPM == "ppm", f"got {sd.PPM!r}")
check("carbon_dioxide unit is ppm",
      sd.FIELD_SENSOR_MAP["carbon_dioxide"].unit == "ppm",
      f"got {sd.FIELD_SENSOR_MAP['carbon_dioxide'].unit!r}")
check("carbon_dioxide_warning_threshold unit is ppm",
      sd.FIELD_SENSOR_MAP["carbon_dioxide_warning_threshold"].unit == "ppm",
      f"got {sd.FIELD_SENSOR_MAP['carbon_dioxide_warning_threshold'].unit!r}")

# ── HA >= 2026.7: UnitOfRatio present ──────────────────────────────────────
print("\nHA >= 2026.7 (UnitOfRatio present):")
had_native = hasattr(ha_const, "UnitOfRatio")
native = getattr(ha_const, "UnitOfRatio", None)
ha_const.UnitOfRatio = native if had_native else _FakeUnitOfRatio
try:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sd = reload_sensor_defs()
    check("prefers UnitOfRatio.PARTS_PER_MILLION",
          sd.PPM is ha_const.UnitOfRatio.PARTS_PER_MILLION, f"got {sd.PPM!r}")
    check("still equals 'ppm'", sd.PPM == "ppm", f"got {sd.PPM!r}")
    check("no deprecation warning raised",
          not [w for w in caught if "CONCENTRATION_PARTS_PER_MILLION" in str(w.message)],
          f"got {[str(w.message) for w in caught]}")
    check("CO2 sensors use the enum",
          sd.FIELD_SENSOR_MAP["carbon_dioxide"].unit
          is ha_const.UnitOfRatio.PARTS_PER_MILLION)
finally:
    if had_native:
        ha_const.UnitOfRatio = native
    else:
        del ha_const.UnitOfRatio

# ── HA < 2026.7: UnitOfRatio absent ────────────────────────────────────────
print("\nHA < 2026.7 (UnitOfRatio absent):")
removed = None
if hasattr(ha_const, "UnitOfRatio"):
    removed = ha_const.UnitOfRatio
    del ha_const.UnitOfRatio
try:
    sd = reload_sensor_defs()
    check("falls back without ImportError", sd is not None)
    check("fallback still yields 'ppm'", sd.PPM == "ppm", f"got {sd.PPM!r}")
    check("CO2 sensors still ppm",
          sd.FIELD_SENSOR_MAP["carbon_dioxide"].unit == "ppm")
finally:
    if removed is not None:
        ha_const.UnitOfRatio = removed

# Leave the module cache holding the real, unpatched import.
reload_sensor_defs()

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
