"""Regression test: the coordinator retains last-good hub status on a transient
fetch failure instead of blanking it.

Issue #82: when an individual getDeviceStatus call fails (e.g. an exhausted 503
after retries), the coordinator substituted an empty status list, which made
every entity on that hub flip Unavailable for a poll cycle. It should instead
reuse the previous poll's status for that hub so entities hold their last-good
values through a passing cloud blip.

Runs in the ha-test container against the deployed integration at /config.
"""
import sys

sys.path.insert(0, "/config")

from custom_components.homgar.coordinator import (  # noqa: E402
    _status_on_fetch_failure,
    _MAX_STALE_STATUS_POLLS,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


MAX = _MAX_STALE_STATUS_POLLS
prior = {"subDeviceStatus": [{"id": "D5", "value": "1,-55,1;0,124,0,0,0,0"}]}

# A brief blip (first few consecutive misses) retains the prior reading verbatim
# so entities hold last-good values instead of flicking Unavailable.
check(
    "retains prior status on the first miss",
    _status_on_fetch_failure(prior, 1, MAX) == prior,
    f"got {_status_on_fetch_failure(prior, 1, MAX)!r}",
)
check(
    "still retains at the miss threshold",
    _status_on_fetch_failure(prior, MAX, MAX) == prior,
    f"got {_status_on_fetch_failure(prior, MAX, MAX)!r}",
)

# A persistent outage must eventually stop masking the problem: once the misses
# exceed the cap, blank the hub so its entities go Unavailable (a visible signal)
# rather than showing stale "watering" state forever.
check(
    "blanks once misses exceed the cap",
    _status_on_fetch_failure(prior, MAX + 1, MAX) == {"subDeviceStatus": []},
    f"got {_status_on_fetch_failure(prior, MAX + 1, MAX)!r}",
)

# No prior reading (first poll, or never succeeded) -> empty, not a crash.
check(
    "falls back to empty status when there is no prior reading",
    _status_on_fetch_failure(None, 1, MAX) == {"subDeviceStatus": []},
    f"got {_status_on_fetch_failure(None, 1, MAX)!r}",
)

# A prior status that itself was empty must not masquerade as good data.
check(
    "an empty prior status stays empty",
    _status_on_fetch_failure({"subDeviceStatus": []}, 1, MAX) == {"subDeviceStatus": []},
    f"got {_status_on_fetch_failure({'subDeviceStatus': []}, 1, MAX)!r}",
)

check("cap is a sane bounded number of polls (2-30)", 2 <= MAX <= 30, f"MAX={MAX}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
