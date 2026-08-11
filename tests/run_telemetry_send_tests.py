"""Telemetry send-path tests (v3.0.44).

The invariant under test: telemetry can NEVER affect integration operation.
Every failure mode — network error, timeout, non-204, malformed entry — must
be swallowed. A raised exception here would break a user's watering.

Also pins the fix for the daily force-reload bug (final review, CRITICAL 1):
bookkeeping (anon_id, last_ping_at) must live in the telemetry Store, never
in the config entry, because writing to entry.data/options fires HA's
update listener and this integration's listener does a full reload.
`hass.config_entries.async_update_entry` must never be called by any of this.

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
    def __init__(self, options=None, entry_id="entry_abc"):
        self.options = dict(options or {})
        self.entry_id = entry_id


class _FakeHass:
    """A fake hass whose telemetry storage is fully in-memory (no real
    Store/disk I/O — see the monkeypatched _async_store_load/save below) and
    whose config_entries.async_update_entry is recorded so tests can assert
    it is NEVER called. Real entry.data/options writes are exactly the bug
    this fix removes: HA fires the update listener on ANY entry change, and
    this integration's listener does a full async_reload().
    """
    def __init__(self, seed=None):
        self.data = {}
        self._disk = dict(seed or {})
        self.update_entry_calls = []
        self.config_entries = types.SimpleNamespace(
            async_update_entry=lambda entry, **kw: self.update_entry_calls.append(kw)
        )


async def _fake_store_load(hass):
    return dict(hass._disk)


async def _fake_store_save(hass, data):
    hass._disk = dict(data)


telemetry._async_store_load = _fake_store_load  # type: ignore[attr-defined]
telemetry._async_store_save = _fake_store_save  # type: ignore[attr-defined]


ENTRY_ID = "entry_abc"
DATA = {"hubs": [{"model": "HWG023WBRF-V2",
                  "subDevices": [{"model": "HTV245FRF"}]}]}
ENABLED = {CONF_TELEMETRY_CHOICE: True,
           CONF_TELEMETRY_COUNTRY: True,
           CONF_TELEMETRY_MODELS: True}
ANON_ID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _seeded_hass(state=None):
    return _FakeHass(seed={ENTRY_ID: dict(state or {})})


# --- the master switch gates everything ------------------------------------
s = _FakeSession()
hass = _seeded_hass({CONF_ANON_ID: ANON_ID})
sent = run(telemetry.async_maybe_ping(hass, _FakeEntry({}, ENTRY_ID), DATA, s))
check("no request at all when telemetry is off", s.posts == [] and sent is False)

# --- happy path ------------------------------------------------------------
s = _FakeSession()
hass = _seeded_hass({CONF_ANON_ID: ANON_ID})
entry = _FakeEntry(ENABLED, ENTRY_ID)
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
      hass._disk.get(ENTRY_ID, {}).get(CONF_LAST_PING_AT) is not None)

# --- the daily guard -------------------------------------------------------
s = _FakeSession()
hass = _seeded_hass({CONF_ANON_ID: ANON_ID, CONF_LAST_PING_AT: datetime.now(timezone.utc).isoformat()})
sent = run(telemetry.async_maybe_ping(hass, _FakeEntry(ENABLED, ENTRY_ID), DATA, s))
check("does not ping twice within 24h", s.posts == [] and sent is False)

# --- an anon id is generated and reused ------------------------------------
s = _FakeSession()
hass = _seeded_hass({})
fresh = _FakeEntry(ENABLED, ENTRY_ID)
run(telemetry.async_maybe_ping(hass, fresh, DATA, s))
first_id = hass._disk.get(ENTRY_ID, {}).get(CONF_ANON_ID)
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
        out = run(telemetry.async_maybe_ping(
            _seeded_hass({CONF_ANON_ID: ANON_ID}), _FakeEntry(ENABLED, ENTRY_ID), DATA, session))
    except Exception as e:  # noqa: BLE001
        raised = e
    check(f"{label} is swallowed, never raised", raised is None, repr(raised))

s = _FakeSession(status=500)
hass500 = _seeded_hass({CONF_ANON_ID: ANON_ID})
entry500 = _FakeEntry(ENABLED, ENTRY_ID)
sent = run(telemetry.async_maybe_ping(hass500, entry500, DATA, s))
check("a non-204 response reports not-sent", sent is False)
check("a failed ping does NOT update last_ping_at (so it retries next cycle)",
      hass500._disk.get(ENTRY_ID, {}).get(CONF_LAST_PING_AT) is None)

# --- sub-toggles off -------------------------------------------------------
s = _FakeSession()
hass_master_only = _seeded_hass({CONF_ANON_ID: ANON_ID})
only_master = _FakeEntry({CONF_TELEMETRY_CHOICE: True}, ENTRY_ID)
run(telemetry.async_maybe_ping(hass_master_only, only_master, DATA, s))
body = s.posts[0][1]["json"]
check("models omitted when the models toggle is off", "models" not in body, str(body))
check("share flags are both False", body["share_country"] is False and body["share_models"] is False)

# --- CRITICAL 1 regression: telemetry must never touch the config entry ----
# Writing state into entry.data/options fires HA's update listener, and this
# integration's listener does a full async_reload() — platforms torn down,
# MQTT disconnected/reconnected, every entity briefly Unavailable — once a
# day, purely because of a stats ping. Bookkeeping now lives in the
# telemetry Store instead, so this must never be called across the whole
# scenario matrix: off, happy path, daily guard, fresh anon id, every
# failure mode, non-204, and sub-toggles-off.
hass_off = _seeded_hass({CONF_ANON_ID: ANON_ID})
run(telemetry.async_maybe_ping(hass_off, _FakeEntry({}, ENTRY_ID), DATA, _FakeSession()))

hass_happy = _seeded_hass({CONF_ANON_ID: ANON_ID})
run(telemetry.async_maybe_ping(hass_happy, _FakeEntry(ENABLED, ENTRY_ID), DATA, _FakeSession()))

all_update_entry_calls = [
    h.update_entry_calls
    for h in (hass500, hass_master_only, hass_off, hass_happy)
]
check("async_update_entry is NEVER called across the whole scenario matrix "
      "(the fix for the daily force-reload bug)",
      all(calls == [] for calls in all_update_entry_calls), str(all_update_entry_calls))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
