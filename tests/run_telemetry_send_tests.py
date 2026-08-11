"""Telemetry send-path tests (v3.0.44).

The invariant under test: telemetry can NEVER affect integration operation.
Every failure mode — network error, timeout, non-204, malformed entry — must
be swallowed. A raised exception here would break a user's watering.

Runs in the ha-test container against the deployed integration at /config.
"""
import asyncio
import sys
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/config")

from custom_components.homgar import telemetry  # noqa: E402
from custom_components.homgar.const import (  # noqa: E402
    CONF_ANON_ID,
    CONF_LAST_PING_AT,
    CONF_TELEMETRY_CHOICE,
    CONF_TELEMETRY_COUNTRY,
    CONF_TELEMETRY_MODELS,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


class _FakeResp:
    def __init__(self, status):
        self.status = status
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def text(self):
        return ""


class _FakeSession:
    """Records posts; optionally raises to simulate network failure."""
    def __init__(self, status=204, raises=None):
        self.status, self.raises, self.posts = status, raises, []
    def post(self, url, **kw):
        self.posts.append((url, kw))
        if self.raises:
            raise self.raises
        return _FakeResp(self.status)


class _FakeEntry:
    def __init__(self, data=None, options=None):
        self.data = dict(data or {})
        self.options = dict(options or {})
        self.entry_id = "entry_abc"


class _FakeHass:
    """Captures async_update_entry so we can assert the timestamp is stored."""
    def __init__(self):
        self.updated = []
        self.config_entries = types.SimpleNamespace(
            async_update_entry=lambda entry, data=None, **kw: (
                entry.data.update(data or {}), self.updated.append(data)
            )
        )


DATA = {"hubs": [{"model": "HWG023WBRF-V2",
                  "subDevices": [{"model": "HTV245FRF"}]}]}
ENABLED = {CONF_TELEMETRY_CHOICE: True,
           CONF_TELEMETRY_COUNTRY: True,
           CONF_TELEMETRY_MODELS: True}
ANON = {CONF_ANON_ID: "3f2504e0-4f89-41d3-9a0c-0305e82c3301"}


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# --- the master switch gates everything ------------------------------------
s = _FakeSession()
sent = run(telemetry.async_maybe_ping(_FakeHass(), _FakeEntry(ANON, {}), DATA, s))
check("no request at all when telemetry is off", s.posts == [] and sent is False)

# --- happy path ------------------------------------------------------------
s = _FakeSession()
hass = _FakeHass()
entry = _FakeEntry(ANON, ENABLED)
sent = run(telemetry.async_maybe_ping(hass, entry, DATA, s))
check("posts once when enabled and due", len(s.posts) == 1 and sent is True)
url, kw = s.posts[0]
check("posts to the telemetry endpoint", url == telemetry.TELEMETRY_URL, url)
body = kw.get("json") or {}
check("body carries the models opted into", body.get("models") == ["HTV245FRF", "HWG023WBRF-V2"],
      f"got {body.get('models')}")
check("body never contains a location field",
      not any(k in body for k in ("country", "city", "latitude", "longitude")))
check("last_ping_at is persisted after a successful ping",
      entry.data.get(CONF_LAST_PING_AT) is not None)

# --- the daily guard -------------------------------------------------------
s = _FakeSession()
recent = _FakeEntry({**ANON, CONF_LAST_PING_AT: datetime.now(timezone.utc).isoformat()}, ENABLED)
sent = run(telemetry.async_maybe_ping(_FakeHass(), recent, DATA, s))
check("does not ping twice within 24h", s.posts == [] and sent is False)

# --- an anon id is generated and reused ------------------------------------
s = _FakeSession()
hass = _FakeHass()
fresh = _FakeEntry({}, ENABLED)
run(telemetry.async_maybe_ping(hass, fresh, DATA, s))
first_id = fresh.data.get(CONF_ANON_ID)
check("an anon id is generated when absent", bool(first_id))
check("the anon id is a uuid4, not derived from anything",
      len(str(first_id)) == 36 and str(first_id).count("-") == 4, str(first_id))

# --- failures must never propagate -----------------------------------------
for label, session in (
    ("connection error", _FakeSession(raises=OSError("no route to host"))),
    ("timeout", _FakeSession(raises=asyncio.TimeoutError())),
    ("unexpected exception", _FakeSession(raises=RuntimeError("boom"))),
):
    raised = None
    try:
        out = run(telemetry.async_maybe_ping(_FakeHass(), _FakeEntry(ANON, ENABLED), DATA, session))
    except Exception as e:  # noqa: BLE001
        raised = e
    check(f"{label} is swallowed, never raised", raised is None, repr(raised))

s = _FakeSession(status=500)
entry500 = _FakeEntry(ANON, ENABLED)
sent = run(telemetry.async_maybe_ping(_FakeHass(), entry500, DATA, s))
check("a non-204 response reports not-sent", sent is False)
check("a failed ping does NOT update last_ping_at (so it retries next cycle)",
      entry500.data.get(CONF_LAST_PING_AT) is None)

# --- sub-toggles off -------------------------------------------------------
s = _FakeSession()
only_master = _FakeEntry(ANON, {CONF_TELEMETRY_CHOICE: True})
run(telemetry.async_maybe_ping(_FakeHass(), only_master, DATA, s))
body = s.posts[0][1]["json"]
check("models omitted when the models toggle is off", "models" not in body, str(body))
check("share flags are both False", body["share_country"] is False and body["share_models"] is False)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
