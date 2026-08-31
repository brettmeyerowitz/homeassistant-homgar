"""Every sensor definition must be a combination Home Assistant accepts.

Issue #103: v3.0.48 set ``last_water_volume`` to ``state_class: measurement``
to stop it producing bogus statistics (#96). That fixed the statistics but
created a new problem — Home Assistant does not allow ``measurement`` with
``device_class: water``, so every affected entity logged a warning on each
startup:

    Entity sensor...last_session_volume is using state class 'measurement'
    which is impossible considering device class ('water') it is using;
    expected None or one of 'total_increasing', 'total'

The correct value for a per-session snapshot is **no state class at all**:
``device_class: water`` is retained so the value is presented and converted as a
volume, while the absence of a state class means Home Assistant derives no
long-term statistics from it — which was the whole point of the #96 fix.

Rather than assert only the field that broke, this validates every definition
we ship against Home Assistant's own ``DEVICE_CLASS_STATE_CLASSES`` table, so
the entire class of mistake is caught here instead of in a user's log.

Runs in the ha-test container against the deployed integration at /config.
"""
import sys

sys.path.insert(0, "/config")

from homeassistant.components.sensor import DEVICE_CLASS_STATE_CLASSES  # noqa: E402

from custom_components.homgar.sensor_defs import FIELD_SENSOR_MAP  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


print("\n🧪 every device_class / state_class pair is one Home Assistant permits")

checked = 0
for field, sdef in sorted(FIELD_SENSOR_MAP.items()):
    if sdef is None:
        continue
    device_class = getattr(sdef, "device_class", None)
    state_class = getattr(sdef, "state_class", None)
    # A definition that declares neither, or omits the state class, is always
    # fine — Home Assistant only constrains the combination of the two.
    if device_class is None or state_class is None:
        continue
    allowed = DEVICE_CLASS_STATE_CLASSES.get(device_class)
    if allowed is None:
        continue
    checked += 1
    check(
        f"{field} ({device_class.value} / {state_class.value})",
        state_class in allowed,
        f"allowed: {sorted(s.value for s in allowed)}",
    )

check("at least one pair was actually validated", checked > 0,
      "the table lookup silently matched nothing — the guard is not working")


print("\n🧪 the specific regression from #103")

lwv = FIELD_SENSOR_MAP["last_water_volume"]
# Not 'measurement' (impossible for water), and not 'total'/'total_increasing'
# either — those are what produced the negative Energy dashboard figures in #96,
# because a per-session snapshot is not a meter.
check(
    "last_water_volume declares no state class at all",
    lwv.state_class is None,
    f"got {lwv.state_class!r}",
)
check(
    "last_water_volume keeps device_class water for unit handling",
    lwv.device_class is not None and lwv.device_class.value == "water",
    f"got {lwv.device_class!r}",
)


print("\n" + "=" * 50)
print(f"Results: {PASS}/{PASS + FAIL} passed, {FAIL} failed")
if FAIL:
    print("❌ TESTS FAILED")
    sys.exit(1)
print("✅ ALL TESTS PASSED")
