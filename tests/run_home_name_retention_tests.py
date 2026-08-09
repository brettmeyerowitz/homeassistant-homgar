"""Regression test: the coordinator retains last-good home names when the
list_homes fetch fails, and logs the failure quietly when it does.

Issue #82 follow-up. v3.0.42 added transient retry and last-good retention for
per-hub *status*, but the home-name map was still rebuilt from scratch every
cycle and left empty when list_homes failed. Reported on 2026-08-08: a single
connection timeout produced two WARNING entries for one event — one from the
client ("failed after 4 attempts") and one from the coordinator ("could not
fetch home names") — even though the cycle carried on and entities were fine.

An empty map is not harmless: hub_copy["homeName"] falls back to "", and
areas.py skips area seeding entirely for a blank name. Retaining the previous
map keeps that working through a blip. Home names are effectively static, so
stale ones carry no risk — unlike stale status, this needs no staleness cap.

Runs in the ha-test container against the deployed integration at /config.
"""
import sys

sys.path.insert(0, "/config")

from custom_components.homgar.coordinator import (  # noqa: E402
    _home_names_on_fetch_failure,
    _should_warn_home_name_failure,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


cached = {123: "Garden", 456: "Front Yard"}

# A blip after at least one good poll must keep the names, so hubs keep their
# homeName and area seeding keeps working.
check(
    "retains cached home names on failure",
    _home_names_on_fetch_failure(cached) == cached,
    f"got {_home_names_on_fetch_failure(cached)!r}",
)
check(
    "retains indefinitely — no staleness cap for static names",
    _home_names_on_fetch_failure(cached) == cached,
)

# The returned map must not alias the cache, or a later cycle mutating its
# result would corrupt the retained copy.
returned = _home_names_on_fetch_failure(cached)
returned[789] = "Injected"
check(
    "returns a copy, not the cached dict itself",
    cached == {123: "Garden", 456: "Front Yard"},
    f"cache was mutated: {cached!r}",
)

# No cache yet (first poll ever failed) -> empty map, not a crash.
check(
    "falls back to an empty map when nothing is cached",
    _home_names_on_fetch_failure(None) == {},
    f"got {_home_names_on_fetch_failure(None)!r}",
)
check(
    "an empty cache stays empty",
    _home_names_on_fetch_failure({}) == {},
    f"got {_home_names_on_fetch_failure({})!r}",
)

# Log level: quiet when nothing user-visible degraded, loud when names really
# are unavailable. This is what removes the duplicate WARNING pair.
check(
    "does not warn when a cached map covers the failure",
    _should_warn_home_name_failure(cached) is False,
)
check(
    "warns when there is no cache to fall back on",
    _should_warn_home_name_failure(None) is True,
)
check(
    "warns when the cache is empty",
    _should_warn_home_name_failure({}) is True,
)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
