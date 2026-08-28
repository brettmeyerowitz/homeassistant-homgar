"""Tests for water-volume statistics: state class, and the derived running total.

Issue #96: "Last Session Volume" could not drive Home Assistant's Energy/water
dashboard, which showed negative values.

Two distinct defects:

1. ``last_water_volume`` was declared ``SensorStateClass.TOTAL``, which tells HA
   the value is a cumulative meter and makes it derive long-term statistics from
   the deltas between readings. It is not cumulative — it is a per-session
   snapshot that drops back down after each run — so a 10 L session followed by
   a 2 L one recorded a delta of -8 L. A per-session snapshot is MEASUREMENT.

2. With that corrected there is still nothing to put on the dashboard, because
   valves like the HTV245FRF report no cumulative total at all (their dp table
   carries STA_LASTUSAGE but neither STA_WATER_TOTAL nor STA_TOTAL_TODAY). So we
   derive one by accumulating each completed session.

The accumulation is keyed on the session's event timestamp rather than on the
volume changing: two consecutive sessions that happen to use the same volume are
indistinguishable by value alone, and would silently lose a session.

Runs in the ha-test container against the deployed integration at /config.
"""
import sys

sys.path.insert(0, "/config")

from homeassistant.components.sensor import SensorStateClass  # noqa: E402

from custom_components.homgar.sensor_defs import FIELD_SENSOR_MAP  # noqa: E402
from custom_components.homgar.water_total import accumulate_session  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


print("\n🧪 state class — a per-session snapshot is not a meter")

lwv = FIELD_SENSOR_MAP["last_water_volume"]
check(
    "last_water_volume is MEASUREMENT, not TOTAL",
    lwv.state_class == SensorStateClass.MEASUREMENT,
    f"got {lwv.state_class!r}",
)
# The derived total is the one that belongs on the Energy dashboard.
wt = FIELD_SENSOR_MAP.get("water_total")
check("water_total is defined", wt is not None)
check(
    "water_total is TOTAL_INCREASING",
    wt is not None and wt.state_class == SensorStateClass.TOTAL_INCREASING,
    f"got {getattr(wt, 'state_class', None)!r}",
)


print("\n🧪 accumulate_session — one session counted exactly once")

# (total, last_evtime, evtime, volume) -> (new_total, new_evtime)

# First ever observation: adopt the session and count it.
check(
    "first observation counts the session",
    accumulate_session(0.0, None, 1000, 5.5) == (5.5, 1000),
    f"got {accumulate_session(0.0, None, 1000, 5.5)!r}",
)
# Repeated polls of the SAME session must not accumulate again — this is the
# common case, since the coordinator polls every 120s while the value sits.
check(
    "same event time does not double count",
    accumulate_session(5.5, 1000, 1000, 5.5) == (5.5, 1000),
    f"got {accumulate_session(5.5, 1000, 1000, 5.5)!r}",
)
# A new session adds to the running total.
check(
    "a new event time adds the new session",
    accumulate_session(5.5, 1000, 2000, 3.0) == (8.5, 2000),
    f"got {accumulate_session(5.5, 1000, 2000, 3.0)!r}",
)
# The bug that value-based change detection would cause: two consecutive
# sessions of identical volume must both be counted.
check(
    "two identical-volume sessions are both counted",
    accumulate_session(5.0, 1000, 2000, 5.0) == (10.0, 2000),
    f"got {accumulate_session(5.0, 1000, 2000, 5.0)!r}",
)

print("\n🧪 accumulate_session — never corrupt the total")

# Missing data must leave the total untouched rather than adding None/zero noise.
check(
    "missing event time leaves the total unchanged",
    accumulate_session(8.5, 2000, None, 4.0) == (8.5, 2000),
    f"got {accumulate_session(8.5, 2000, None, 4.0)!r}",
)
check(
    "missing volume leaves the total unchanged",
    accumulate_session(8.5, 2000, 3000, None) == (8.5, 2000),
    f"got {accumulate_session(8.5, 2000, 3000, None)!r}",
)
# A zero-volume session is a real event (valve opened, nothing flowed). It must
# advance the session key so the NEXT real session is not mistaken for it.
check(
    "a zero-volume session still advances the event key",
    accumulate_session(8.5, 2000, 3000, 0.0) == (8.5, 3000),
    f"got {accumulate_session(8.5, 2000, 3000, 0.0)!r}",
)
# Defensive: a negative volume is never physical and must not reduce a
# TOTAL_INCREASING total, which HA would read as a meter reset.
check(
    "a negative volume is ignored",
    accumulate_session(8.5, 2000, 3000, -2.0) == (8.5, 3000),
    f"got {accumulate_session(8.5, 2000, 3000, -2.0)!r}",
)
# An out-of-order/older event time (clock skew, stale cached payload) must not
# re-count an earlier session.
check(
    "an older event time does not accumulate",
    accumulate_session(8.5, 2000, 1500, 4.0) == (8.5, 2000),
    f"got {accumulate_session(8.5, 2000, 1500, 4.0)!r}",
)

print("\n🧪 accumulate_session — monotonic, as TOTAL_INCREASING requires")

total, ev = 0.0, None
for i, (t, v) in enumerate([(100, 1.0), (100, 1.0), (200, 2.5), (200, 2.5), (300, 0.0), (400, 4.0)]):
    new_total, ev = accumulate_session(total, ev, t, v)
    check(f"step {i}: total never decreases", new_total >= total,
          f"{total} -> {new_total}")
    total = new_total
check("final total is 1.0 + 2.5 + 0.0 + 4.0 = 7.5", total == 7.5, f"got {total}")


print("\n🧪 _needs_derived_water_total — never compete with a hardware meter")

from custom_components.homgar.sensor import _needs_derived_water_total  # noqa: E402

check(
    "a valve reporting only last-session volume gets a derived total",
    _needs_derived_water_total("HTV245FRF", {"last_water_volume": 5.0}) is True,
)
# The important one: a device with a real hardware counter must NOT also get a
# derived meter, or the Energy dashboard offers two totals for one valve.
check(
    "a valve already reporting a hardware total does not",
    _needs_derived_water_total(
        "HTV245FRF", {"last_water_volume": 5.0, "total_water_volume": 120.0}
    ) is False,
)
check(
    "a non-valve device does not",
    _needs_derived_water_total("HCS012ARF", {"last_water_volume": 5.0}) is False,
)
check(
    "a valve reporting no volume at all does not",
    _needs_derived_water_total("HTV245FRF", {"battery_level": 80}) is False,
)
check("an unknown model does not", _needs_derived_water_total(None, {}) is False)


print("\n" + "=" * 50)
print(f"Results: {PASS}/{PASS + FAIL} passed, {FAIL} failed")
if FAIL:
    print("❌ TESTS FAILED")
    sys.exit(1)
print("✅ ALL TESTS PASSED")
