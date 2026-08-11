"""Coordinator telemetry-scheduling tests (final review, IMPORTANT 3).

telemetry.py's import used to sit inside `_async_update_data`'s try block but
outside telemetry's own try/except, and the ping was awaited directly — so
any failure in resolving the session, constructing the coroutine, or
scheduling it could reach `_async_update_data`'s outer `except Exception`
and turn a stats hiccup into `UpdateFailed` (every entity Unavailable), and
an unreachable endpoint could add up to PING_TIMEOUT_SECONDS of latency to
every poll.

The fix moves the telemetry import to module scope, fires the ping via
`hass.async_create_background_task` instead of awaiting it, and wraps the
whole thing in `HomGarCoordinator._fire_telemetry_ping`'s own try/except.
This pins the one invariant that matters: nothing _fire_telemetry_ping does
can ever raise into its caller, even if the scheduling call itself blows up.

Runs in the ha-test container against the deployed integration at /config.
"""
import sys
import types

sys.path.insert(0, "/config")

from custom_components.homgar import coordinator as coordinator_module  # noqa: E402
from custom_components.homgar.coordinator import HomGarCoordinator  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


def _bare_coordinator(hass, entry):
    """Build a HomGarCoordinator without running its real __init__ (which
    needs a live HomeAssistant instance, an API client, etc.) — the method
    under test only touches self.hass and self._entry."""
    coord = HomGarCoordinator.__new__(HomGarCoordinator)
    coord.hass = hass
    coord._entry = entry
    return coord


class _FakeEntry:
    entry_id = "entry_abc"


HUBS = [{"model": "HWG023WBRF-V2", "mid": 1}]


# --- the scheduling call itself blowing up must not propagate --------------
class _RaisingHass:
    """Simulates hass.async_create_background_task raising, e.g. because
    HA refused to schedule a new background task during shutdown."""
    def async_create_background_task(self, coro, name=None):
        coro.close()  # avoid an unawaited-coroutine warning; we never run it
        raise RuntimeError("simulated scheduling failure")


raised = None
try:
    _bare_coordinator(_RaisingHass(), _FakeEntry())._fire_telemetry_ping(HUBS)
except Exception as e:  # noqa: BLE001
    raised = e
check("a raising hass.async_create_background_task does not propagate out of "
      "_fire_telemetry_ping (would otherwise reach _async_update_data's outer "
      "except and fail the whole poll)",
      raised is None, repr(raised))


# --- a failure resolving the session must not propagate --------------------
def _raising_get_clientsession(hass):
    raise RuntimeError("simulated session resolution failure")


original_get_clientsession = coordinator_module.async_get_clientsession
coordinator_module.async_get_clientsession = _raising_get_clientsession
try:
    raised = None
    try:
        _bare_coordinator(_RaisingHass(), _FakeEntry())._fire_telemetry_ping(HUBS)
    except Exception as e:  # noqa: BLE001
        raised = e
    check("a raising async_get_clientsession does not propagate either",
          raised is None, repr(raised))
finally:
    coordinator_module.async_get_clientsession = original_get_clientsession


# --- the happy path actually schedules a background task, not more/less ---
# Real async_get_clientsession() needs a fully-wired HomeAssistant instance
# (hass.bus, shutdown listeners, ...) that this bare coordinator doesn't
# have — fine for the two "must not raise" cases above (a bare fake hass IS
# the failure being simulated there), but this test's job is to confirm the
# scheduling itself works when nothing upstream fails, so stub the session
# resolution out.
coordinator_module.async_get_clientsession = lambda hass: object()
try:
    class _RecordingHass:
        def __init__(self):
            self.scheduled = []
        def async_create_background_task(self, coro, name=None):
            self.scheduled.append(name)
            coro.close()  # never run it — this test only checks scheduling happened

    recording_hass = _RecordingHass()
    raised = None
    try:
        _bare_coordinator(recording_hass, _FakeEntry())._fire_telemetry_ping(HUBS)
    except Exception as e:  # noqa: BLE001
        raised = e
    check("the happy path schedules exactly one background task and does not raise",
          raised is None and recording_hass.scheduled == ["homgar_telemetry_ping"],
          f"raised={raised!r} scheduled={recording_hass.scheduled}")
finally:
    coordinator_module.async_get_clientsession = original_get_clientsession

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
