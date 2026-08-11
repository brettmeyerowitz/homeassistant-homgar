# Opt-in Telemetry — Integration Side (v3.0.44) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in, off-by-default anonymous telemetry to the HomGar/RainPoint integration — three granular toggles, a one-time prompt for existing installs, and a once-daily ping to the already-deployed telemetry worker.

**Architecture:** One new module, `custom_components/homgar/telemetry.py`, owning the anon ID, payload construction, the 24h guard and the send. The coordinator calls a single entry point once per poll cycle; everything else is UX wiring in the existing config flow, options flow and setup path. Telemetry can never affect integration operation.

**Tech Stack:** Home Assistant custom integration (Python 3.13), aiohttp via HA's shared session, standalone test runners executed in the `ha-test` Docker container.

**Spec:** `docs/superpowers/specs/2026-08-11-optin-telemetry-design.md`
**Worker plan (complete, deployed):** `docs/superpowers/plans/2026-08-11-telemetry-worker.md`

## Verified facts — established by spike, do not re-derive

These were measured on 2026-08-11 from inside the `ha-test` container against the live worker. Build on them:

- **Endpoint:** `https://homgar-telemetry-worker.funkypeople.workers.dev/ping`
- **A real HA container reaches it and gets `204` with an empty body.** Confirmed end to end: the payload landed, country aggregated to `ZA`, both device models counted, version recorded.
- **No User-Agent override is needed.** HA's default aiohttp UA was *not* blocked. This is the opposite of the HomGar cloud's behaviour in issue #76 — do **not** copy the `_USER_AGENT = "okhttp/4.9.2"` workaround from `api/client.py` into telemetry. It is unnecessary here and would be misleading.
- **HA version:** `from homeassistant.const import __version__` returns e.g. `"2026.6.4"`.
- **Integration version:** obtain via `homeassistant.loader.async_get_integration(hass, DOMAIN)` → `.version`. Do **not** hardcode it; `const.py` has no version constant and duplicating the manifest value would drift.
- **Device model names** live in the coordinator's data: hub models at `hub["model"]` (set in `coordinator.py:245`) and sub-device models at `sub.get("model")` (`coordinator.py:349`, `:431`), with sub-devices under each hub's `subDevices`.
- **Existing options** are `group_multi_zone_devices` and `valve_duration_unit`, in `HomGarOptionsFlow.async_step_init` (`config_flow.py:345+`), with translations under `options.step.init.data` in `translations/en.json`.

## Global Constraints

- **The worker only ever reads `country`, and only when `share_country` is true.** The client must send `share_country` and `share_models` as explicit booleans, and must **omit the `models` key entirely** when models are not opted in — not send an empty list.
- **All three toggles default OFF.** No telemetry is sent unless the master switch is explicitly enabled.
- **Telemetry must never affect integration operation.** Every failure is swallowed at debug level. 10s timeout. No retries.
- **Never send anything not listed in the payload schema below.** No entity counts, no account details, no email, no home names, no serial numbers, no IP.
- **Storage:** `anon_id` and `last_ping_at` in config entry **data**; the three toggles in config entry **options**.
- **`anon_id` is a random UUID4** generated once, never derived from the account, email, `deviceId`, or any device identifier.
- Ping at most once per 24h per config entry.
- Repo convention: standalone Python test runners under `tests/`, run inside the `ha-test` container, wired into `scripts/pre-commit-docker-test.sh`. The full gate must be green before commit.

### The payload — the complete and only permitted set of fields

```json
{
  "anon_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
  "integration_version": "3.0.44",
  "hass_version": "2026.8.1",
  "share_country": true,
  "share_models": true,
  "models": ["HTV245FRF", "HWG023WBRF-V2"]
}
```

---

### Task 1: `telemetry.py` — anon ID, payload, and the daily guard

Pure logic only. No network, no HA wiring. This keeps the testable core isolated from the parts that need a running HA.

**Files:**
- Create: `custom_components/homgar/telemetry.py`
- Create: `tests/run_telemetry_payload_tests.py`
- Modify: `custom_components/homgar/const.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `CONF_TELEMETRY_CHOICE = "telemetry_choice"`, `CONF_TELEMETRY_COUNTRY = "telemetry_share_country"`, `CONF_TELEMETRY_MODELS = "telemetry_share_models"`, `CONF_ANON_ID = "anon_id"`, `CONF_LAST_PING_AT = "last_ping_at"` (in `const.py`)
  - `TELEMETRY_URL`, `PING_INTERVAL_HOURS = 24`
  - `build_payload(anon_id, integration_version, hass_version, share_country, share_models, models) -> dict`
  - `models_from_coordinator_data(data) -> list[str]`
  - `should_ping(last_ping_at, now, interval_hours) -> bool`
  - `is_telemetry_enabled(options) -> bool`

- [ ] **Step 1: Write the failing test**

`tests/run_telemetry_payload_tests.py`:

```python
"""Telemetry payload/guard tests (v3.0.44, opt-in telemetry).

Pure-logic coverage for the pieces that decide WHAT is sent and WHETHER to
send. The privacy-relevant assertions are the point: the payload must never
carry a field outside the permitted set, and must omit `models` entirely
when models are not opted in.

Runs in the ha-test container against the deployed integration at /config.
"""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/config")

from custom_components.homgar.telemetry import (  # noqa: E402
    build_payload,
    models_from_coordinator_data,
    should_ping,
    is_telemetry_enabled,
    PING_INTERVAL_HOURS,
    TELEMETRY_URL,
)
from custom_components.homgar.const import (  # noqa: E402
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


ID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
PERMITTED = {
    "anon_id", "integration_version", "hass_version",
    "share_country", "share_models", "models",
}

# --- payload shape ---------------------------------------------------------
full = build_payload(ID, "3.0.44", "2026.8.1", True, True, ["HTV245FRF"])
check("payload has no field outside the permitted set",
      set(full) <= PERMITTED, f"extra: {set(full) - PERMITTED}")
check("payload carries the anon id", full["anon_id"] == ID)
check("payload carries both versions",
      full["integration_version"] == "3.0.44" and full["hass_version"] == "2026.8.1")
check("flags are real booleans, not truthy values",
      full["share_country"] is True and full["share_models"] is True)

no_models = build_payload(ID, "3.0.44", "2026.8.1", True, False, ["HTV245FRF"])
check("models key is OMITTED entirely when not opted in",
      "models" not in no_models, f"got {no_models!r}")
check("share_models is still present and False", no_models["share_models"] is False)

no_country = build_payload(ID, "3.0.44", "2026.8.1", False, True, ["HTV245FRF"])
check("share_country False is sent explicitly", no_country["share_country"] is False)

# The client must never send location itself — the worker derives country at
# the edge. Any location-shaped key here would be a privacy regression.
for forbidden in ("country", "city", "latitude", "longitude", "postal_code",
                  "timezone", "region", "ip", "email", "home_name"):
    check(f"payload never contains '{forbidden}'", forbidden not in full)

# --- model extraction ------------------------------------------------------
DATA = {"hubs": [
    {"model": "HWG023WBRF-V2", "subDevices": [
        {"model": "HTV245FRF"}, {"model": "HTV245FRF"}, {"model": None},
    ]},
    {"model": "HWG023WBRF-V2", "subDevices": [{"model": "HCS012ARF"}]},
]}
models = models_from_coordinator_data(DATA)
check("model list is deduplicated and sorted",
      models == ["HCS012ARF", "HTV245FRF", "HWG023WBRF-V2"], f"got {models}")
check("None models are dropped", None not in models)
check("empty data yields an empty list", models_from_coordinator_data({}) == [])

# --- daily guard -----------------------------------------------------------
now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
check("pings when never pinged before", should_ping(None, now, PING_INTERVAL_HOURS) is True)
check("does not ping 1h after the last ping",
      should_ping(now - timedelta(hours=1), now, PING_INTERVAL_HOURS) is False)
check("does not ping at 23h59m",
      should_ping(now - timedelta(hours=23, minutes=59), now, PING_INTERVAL_HOURS) is False)
check("pings at 24h01m",
      should_ping(now - timedelta(hours=24, minutes=1), now, PING_INTERVAL_HOURS) is True)
check("a corrupt last_ping_at does not crash and allows a ping",
      should_ping("not-a-timestamp", now, PING_INTERVAL_HOURS) is True)
check("a future last_ping_at (clock skew) does not ping forever",
      should_ping(now + timedelta(days=400), now, PING_INTERVAL_HOURS) is False)

# --- enablement ------------------------------------------------------------
check("disabled when nothing is set", is_telemetry_enabled({}) is False)
check("disabled when explicitly off",
      is_telemetry_enabled({CONF_TELEMETRY_CHOICE: False}) is False)
check("enabled only when master is on",
      is_telemetry_enabled({CONF_TELEMETRY_CHOICE: True}) is True)
check("sub-toggles alone never enable telemetry",
      is_telemetry_enabled({CONF_TELEMETRY_COUNTRY: True,
                            CONF_TELEMETRY_MODELS: True}) is False)

check("endpoint is the deployed worker over https",
      TELEMETRY_URL.startswith("https://") and TELEMETRY_URL.endswith("/ping"),
      TELEMETRY_URL)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
docker start ha-test >/dev/null; sleep 8
docker exec ha-test mkdir -p /tmp/tests
docker cp custom_components/homgar ha-test:/config/custom_components/ >/dev/null
docker cp tests/run_telemetry_payload_tests.py ha-test:/tmp/tests/ >/dev/null
docker exec ha-test python3 /tmp/tests/run_telemetry_payload_tests.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.homgar.telemetry'`.

- [ ] **Step 3: Add the constants**

Append to `custom_components/homgar/const.py`, after the existing `CONF_VALVE_DURATION_UNIT` line:

```python
# --- Opt-in telemetry (v3.0.44) -------------------------------------------
# Master switch plus two independent sub-toggles, all default OFF. Stored in
# config entry OPTIONS (user-editable via the options flow).
CONF_TELEMETRY_CHOICE = "telemetry_choice"
CONF_TELEMETRY_COUNTRY = "telemetry_share_country"
CONF_TELEMETRY_MODELS = "telemetry_share_models"

# Stored in config entry DATA (must survive restarts, not user-editable).
CONF_ANON_ID = "anon_id"
CONF_LAST_PING_AT = "last_ping_at"
```

- [ ] **Step 4: Write `telemetry.py`**

```python
"""
telemetry.py — opt-in, off-by-default anonymous telemetry.

Answers one question for the maintainer: how many people run this integration
and roughly where. Nothing is sent unless the user explicitly switches it on.

Design notes that matter:
  * The client NEVER sends location. It sends a `share_country` flag; the
    Cloudflare worker derives the country at the edge and stores it only as a
    monthly aggregate that cannot be joined back to an install.
  * `models` is omitted from the payload entirely when not opted in, rather
    than sent as an empty list — the wire format should not imply we asked.
  * `anon_id` is a random UUID4 with no relationship to the account, email or
    any device identifier.
  * No User-Agent override. The HomGar cloud blocks HA's default UA (issue
    #76) but the telemetry worker does not — verified by spike.

See docs/superpowers/specs/2026-08-11-optin-telemetry-design.md
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

_LOGGER = logging.getLogger(__name__)

TELEMETRY_URL = "https://homgar-telemetry-worker.funkypeople.workers.dev/ping"
PING_INTERVAL_HOURS = 24
PING_TIMEOUT_SECONDS = 10


def is_telemetry_enabled(options: dict) -> bool:
    """True only when the master switch is explicitly on.

    The sub-toggles are meaningless on their own — enabling "include my
    country" without the master switch must never cause a request.
    """
    from .const import CONF_TELEMETRY_CHOICE

    return options.get(CONF_TELEMETRY_CHOICE) is True


def build_payload(
    anon_id: str,
    integration_version: str,
    hass_version: str,
    share_country: bool,
    share_models: bool,
    models: list[str] | None,
) -> dict[str, Any]:
    """Build the complete wire payload. This is the ONLY place a payload is
    constructed, so it is the single place to audit what leaves a user's
    machine."""
    payload: dict[str, Any] = {
        "anon_id": anon_id,
        "integration_version": integration_version,
        "hass_version": hass_version,
        "share_country": bool(share_country),
        "share_models": bool(share_models),
    }
    if share_models:
        payload["models"] = list(models or [])
    return payload


def models_from_coordinator_data(data: dict | None) -> list[str]:
    """Extract the distinct device model names from a coordinator payload.

    Model names only — never serial numbers, addresses, names or home IDs.
    """
    if not data:
        return []
    found: set[str] = set()
    for hub in data.get("hubs") or []:
        model = hub.get("model")
        if model and model != "Unknown":
            found.add(str(model))
        for sub in hub.get("subDevices") or []:
            sub_model = sub.get("model")
            if sub_model:
                found.add(str(sub_model))
    return sorted(found)


def should_ping(
    last_ping_at: Any, now: datetime, interval_hours: int = PING_INTERVAL_HOURS
) -> bool:
    """Whether enough time has passed since the last successful ping.

    Tolerates a missing, malformed or future timestamp: a corrupt value must
    never wedge telemetry permanently on or permanently off. A future value
    (clock skew, restored backup) blocks until it passes rather than pinging
    every cycle.
    """
    if last_ping_at is None:
        return True
    if isinstance(last_ping_at, str):
        try:
            last_ping_at = datetime.fromisoformat(last_ping_at)
        except (TypeError, ValueError):
            return True
    if not isinstance(last_ping_at, datetime):
        return True
    if last_ping_at.tzinfo is None:
        last_ping_at = last_ping_at.replace(tzinfo=timezone.utc)
    if last_ping_at > now:
        return False
    return now - last_ping_at >= timedelta(hours=interval_hours)
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
docker cp custom_components/homgar ha-test:/config/custom_components/ >/dev/null
docker exec ha-test python3 /tmp/tests/run_telemetry_payload_tests.py
```

Expected: PASS, 26 checks.

- [ ] **Step 6: Commit**

```bash
git add custom_components/homgar/telemetry.py custom_components/homgar/const.py tests/run_telemetry_payload_tests.py
git commit -m "feat(telemetry): payload construction, model extraction and daily guard

Pure logic, no network and no HA wiring, so the part that decides what leaves
a user's machine is isolated and directly testable.

build_payload is the single place a payload is constructed, and the tests
assert it can never carry a field outside the permitted set. models is
omitted entirely when not opted in rather than sent empty."
```

---

### Task 2: The sender, and the coordinator hook

**Files:**
- Modify: `custom_components/homgar/telemetry.py`
- Modify: `custom_components/homgar/coordinator.py`
- Create: `tests/run_telemetry_send_tests.py`

**Interfaces:**
- Consumes: everything from Task 1
- Produces: `async def async_maybe_ping(hass, entry, coordinator_data, session) -> bool` — returns True if a ping was sent and the timestamp updated

- [ ] **Step 1: Write the failing test**

`tests/run_telemetry_send_tests.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

```bash
docker cp tests/run_telemetry_send_tests.py ha-test:/tmp/tests/ >/dev/null
docker exec ha-test python3 /tmp/tests/run_telemetry_send_tests.py
```

Expected: FAIL — `AttributeError: module ... has no attribute 'async_maybe_ping'`.

- [ ] **Step 3: Add the sender to `telemetry.py`**

```python
async def async_maybe_ping(hass, entry, coordinator_data, session) -> bool:
    """Send one telemetry ping if enabled and due. Returns True if sent.

    This function must NEVER raise. It runs inside the coordinator's poll
    cycle, and a user's irrigation must not depend on a stats endpoint being
    reachable. Every failure path is swallowed at debug level.
    """
    from uuid import uuid4

    from .const import (
        CONF_ANON_ID,
        CONF_LAST_PING_AT,
        CONF_TELEMETRY_COUNTRY,
        CONF_TELEMETRY_MODELS,
    )

    try:
        options = dict(getattr(entry, "options", {}) or {})
        if not is_telemetry_enabled(options):
            return False

        data = dict(getattr(entry, "data", {}) or {})
        now = datetime.now(timezone.utc)
        if not should_ping(data.get(CONF_LAST_PING_AT), now):
            return False

        anon_id = data.get(CONF_ANON_ID)
        if not anon_id:
            anon_id = str(uuid4())
            hass.config_entries.async_update_entry(
                entry, data={**data, CONF_ANON_ID: anon_id}
            )
            data = {**data, CONF_ANON_ID: anon_id}

        share_country = options.get(CONF_TELEMETRY_COUNTRY) is True
        share_models = options.get(CONF_TELEMETRY_MODELS) is True

        payload = build_payload(
            anon_id,
            await _async_integration_version(hass),
            _hass_version(),
            share_country,
            share_models,
            models_from_coordinator_data(coordinator_data) if share_models else None,
        )

        import aiohttp

        async with session.post(
            TELEMETRY_URL,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=PING_TIMEOUT_SECONDS),
        ) as resp:
            if resp.status != 204:
                _LOGGER.debug("Telemetry ping returned HTTP %s", resp.status)
                return False

        # Only stamp on success, so a failed ping retries on the next cycle
        # rather than being silently skipped for a day.
        hass.config_entries.async_update_entry(
            entry, data={**data, CONF_LAST_PING_AT: now.isoformat()}
        )
        _LOGGER.debug("Telemetry ping sent")
        return True
    except Exception as err:  # noqa: BLE001 - telemetry must never break setup
        _LOGGER.debug("Telemetry ping failed (ignored): %s", err)
        return False


def _hass_version() -> str:
    try:
        from homeassistant.const import __version__

        return str(__version__)
    except Exception:  # noqa: BLE001
        return "unknown"


async def _async_integration_version(hass) -> str:
    """Read the version from manifest.json rather than duplicating it."""
    try:
        from homeassistant.loader import async_get_integration

        from .const import DOMAIN

        integration = await async_get_integration(hass, DOMAIN)
        return str(integration.version)
    except Exception:  # noqa: BLE001
        return "unknown"
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
docker cp custom_components/homgar ha-test:/config/custom_components/ >/dev/null
docker exec ha-test python3 /tmp/tests/run_telemetry_send_tests.py
```

Expected: PASS, 16 checks.

- [ ] **Step 5: Hook it into the coordinator**

In `custom_components/homgar/coordinator.py`, at the very end of the successful
path of `_async_update_data` — immediately before the `return` of the assembled
result, and INSIDE the existing `try` — add:

```python
            # Opt-in telemetry. Off by default; never raises. Placed last so a
            # telemetry problem cannot affect the data this cycle produced.
            from .telemetry import async_maybe_ping
            from homeassistant.helpers.aiohttp_client import async_get_clientsession

            result_for_telemetry = {"hubs": hubs}
            await async_maybe_ping(
                self.hass, self._entry, result_for_telemetry,
                async_get_clientsession(self.hass),
            )
```

- [ ] **Step 6: Run the full Docker gate**

```bash
bash scripts/pre-commit-docker-test.sh
```

Expected: all existing suites still green (telemetry is off by default, so no
behaviour changes).

- [ ] **Step 7: Commit**

```bash
git add custom_components/homgar/telemetry.py custom_components/homgar/coordinator.py tests/run_telemetry_send_tests.py
git commit -m "feat(telemetry): daily ping piggybacked on the coordinator cycle

The send is wrapped so it can never raise into the poll cycle — a user's
irrigation must not depend on a stats endpoint being reachable. Tests cover
connection errors, timeouts, unexpected exceptions and non-204 responses.

last_ping_at is stamped only on success, so a failed ping retries next cycle
instead of being silently skipped for a day."
```

---

### Task 3: Opt-in UX — options flow, config flow, and the one-time prompt

**Files:**
- Modify: `custom_components/homgar/config_flow.py`
- Modify: `custom_components/homgar/__init__.py`
- Modify: `custom_components/homgar/translations/en.json`
- Create: `tests/run_telemetry_optin_tests.py`

**Interfaces:**
- Consumes: the constants from Task 1
- Produces: `async_prompt_for_telemetry_once(hass, entry) -> bool` in `telemetry.py`

- [ ] **Step 1: Write the failing test**

`tests/run_telemetry_optin_tests.py`:

```python
"""Opt-in prompt tests (v3.0.44).

The prompt must appear exactly once for an existing install that has never
answered, and never again once any choice — including "no" — is recorded.
A nagging privacy prompt is worse than no prompt.

Runs in the ha-test container against the deployed integration at /config.
"""
import asyncio
import sys
import types

sys.path.insert(0, "/config")

from custom_components.homgar import telemetry  # noqa: E402
from custom_components.homgar.const import CONF_TELEMETRY_CHOICE  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


class _FakeEntry:
    def __init__(self, options=None):
        self.options = dict(options or {})
        self.entry_id = "entry_abc"
        self.title = "HomGar"


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


created = []


def _fake_create(hass, message, title=None, notification_id=None):
    created.append({"message": message, "title": title, "id": notification_id})


telemetry._async_create_notification = _fake_create  # type: ignore[attr-defined]

# unset -> prompt
created.clear()
shown = run(telemetry.async_prompt_for_telemetry_once(object(), _FakeEntry()))
check("prompts when the choice has never been made", shown is True and len(created) == 1)
check("uses a stable notification id",
      created[0]["id"] == "homgar_telemetry_optin", str(created[0]["id"]))
check("the prompt says it is optional and off by default",
      "optional" in created[0]["message"].lower()
      and "off by default" in created[0]["message"].lower())
check("the prompt links to the integration settings",
      "/config/integrations" in created[0]["message"])
check("the prompt discloses that versions are included",
      "version" in created[0]["message"].lower())

# answered yes -> silent
created.clear()
shown = run(telemetry.async_prompt_for_telemetry_once(
    object(), _FakeEntry({CONF_TELEMETRY_CHOICE: True})))
check("never prompts again once opted in", shown is False and created == [])

# answered no -> silent (the important case: declining must not nag)
created.clear()
shown = run(telemetry.async_prompt_for_telemetry_once(
    object(), _FakeEntry({CONF_TELEMETRY_CHOICE: False})))
check("never prompts again once declined", shown is False and created == [])

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
docker cp tests/run_telemetry_optin_tests.py ha-test:/tmp/tests/ >/dev/null
docker exec ha-test python3 /tmp/tests/run_telemetry_optin_tests.py
```

Expected: FAIL — `async_prompt_for_telemetry_once` does not exist.

- [ ] **Step 3: Add the prompt to `telemetry.py`**

```python
def _async_create_notification(hass, message, title=None, notification_id=None):
    """Indirection so tests can capture the notification without a real hass."""
    from homeassistant.components import persistent_notification

    persistent_notification.async_create(
        hass, message, title=title, notification_id=notification_id
    )


TELEMETRY_NOTIFICATION_ID = "homgar_telemetry_optin"

_OPTIN_MESSAGE = (
    "This integration can optionally report **anonymous** usage data, so I can "
    "see how many people use it and roughly where in the world they are. It is "
    "**off by default** and entirely your choice.\n\n"
    "If you switch it on you choose separately whether to include your country "
    "and your device models. The base data is an anonymous random ID plus the "
    "Home Assistant and integration version numbers.\n\n"
    "No account details, no location beyond an optional country, and your IP is "
    "never stored.\n\n"
    "[Open settings](/config/integrations/integration/homgar) — or ignore this; "
    "it will not ask again."
)


async def async_prompt_for_telemetry_once(hass, entry) -> bool:
    """Show the opt-in prompt if the user has never answered. Returns True if
    shown.

    Fires only when no choice exists. Recording any answer — including "no" —
    stops it permanently.
    """
    from .const import CONF_TELEMETRY_CHOICE

    try:
        options = dict(getattr(entry, "options", {}) or {})
        if CONF_TELEMETRY_CHOICE in options:
            return False
        _async_create_notification(
            hass,
            _OPTIN_MESSAGE,
            title="HomGar/RainPoint: optional anonymous usage data",
            notification_id=TELEMETRY_NOTIFICATION_ID,
        )
        return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Telemetry opt-in prompt failed (ignored): %s", err)
        return False
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
docker cp custom_components/homgar ha-test:/config/custom_components/ >/dev/null
docker exec ha-test python3 /tmp/tests/run_telemetry_optin_tests.py
```

Expected: PASS, 7 checks.

- [ ] **Step 5: Add the three toggles to the options flow**

In `custom_components/homgar/config_flow.py`, import the new constants
alongside the existing ones, then in `HomGarOptionsFlow.async_step_init`, add
to the `vol.Schema` dict after `CONF_VALVE_DURATION_UNIT`:

```python
                vol.Optional(
                    CONF_TELEMETRY_CHOICE,
                    default=self._config_entry.options.get(CONF_TELEMETRY_CHOICE, False),
                ): bool,
                vol.Optional(
                    CONF_TELEMETRY_COUNTRY,
                    default=self._config_entry.options.get(CONF_TELEMETRY_COUNTRY, False),
                ): bool,
                vol.Optional(
                    CONF_TELEMETRY_MODELS,
                    default=self._config_entry.options.get(CONF_TELEMETRY_MODELS, False),
                ): bool,
```

Then, still in `async_step_init`, immediately after `if user_input is not None:`
and before `return self.async_create_entry(...)`, clear the prompt:

```python
            from homeassistant.components import persistent_notification

            from .telemetry import TELEMETRY_NOTIFICATION_ID

            persistent_notification.async_dismiss(
                self.hass, TELEMETRY_NOTIFICATION_ID
            )
```

- [ ] **Step 6: Add translations**

In `custom_components/homgar/translations/en.json`, add to
`options.step.init.data`:

```json
        "telemetry_choice": "Share anonymous usage data (off by default)",
        "telemetry_share_country": "  └ Include my country",
        "telemetry_share_models": "  └ Include my device models"
```

- [ ] **Step 7: Fire the prompt at setup**

In `custom_components/homgar/__init__.py`, inside `async_setup_entry`, after the
device layout is finalised (near the existing `"Device layout finalized"` log
line), add:

```python
        from .telemetry import async_prompt_for_telemetry_once

        await async_prompt_for_telemetry_once(hass, entry)
```

- [ ] **Step 8: Wire all three suites into the gate**

In `scripts/pre-commit-docker-test.sh`, before the
`# ── Test: decoder regression suite` block, add:

```bash
# ── Test: opt-in telemetry (v3.0.44) ──────────────────────────────────────
for suite in run_telemetry_payload_tests run_telemetry_send_tests run_telemetry_optin_tests; do
    echo "🧪 Running ${suite}..."
    docker cp "tests/${suite}.py" "ha-test:/tmp/tests/${suite}.py" > /dev/null
    if docker exec ha-test python3 "/tmp/tests/${suite}.py"; then
        echo "✅ ${suite} passed"
    else
        echo "❌ ERROR: ${suite} failed"
        exit 1
    fi
done
```

- [ ] **Step 9: Run the full gate**

```bash
bash scripts/pre-commit-docker-test.sh
```

Expected: everything green, including the three new suites.

- [ ] **Step 10: Verify the prompt appears in the real UI**

```bash
docker restart ha-test >/dev/null && sleep 45
docker exec ha-test grep -i "telemetry" /config/home-assistant.log | tail -5
```

Then open `http://localhost:8123`, confirm the notification appears once, open
**Settings → Devices & Services → HomGar → Configure**, confirm the three
toggles render with the sub-toggle indentation, save with everything off, and
confirm the notification clears and does not return after another restart.

- [ ] **Step 11: Commit**

```bash
git add custom_components/homgar/telemetry.py custom_components/homgar/config_flow.py \
        custom_components/homgar/__init__.py custom_components/homgar/translations/en.json \
        tests/run_telemetry_optin_tests.py scripts/pre-commit-docker-test.sh
git commit -m "feat(telemetry): opt-in UX with a one-time prompt for existing installs

A config-flow change reaches new installs only and an options flow is
pull-only, so existing installs get a single persistent notification when no
choice has been recorded. Saving any choice — including no — clears it
permanently. A nagging privacy prompt is worse than no prompt."
```

---

### Task 4: Release 3.0.44

**Files:**
- Modify: `custom_components/homgar/manifest.json`
- Modify: `CHANGELOG.md`
- Modify: `README.md`

- [ ] **Step 1: Bump the manifest**

`custom_components/homgar/manifest.json`: `"version": "3.0.44"`.

- [ ] **Step 2: Add the changelog entry**

Add a `## [3.0.44] - <today>` section above `## [3.0.43]`, describing: the
opt-in telemetry, that it is off by default, the three granular toggles, what
is and is not collected, the one-time prompt, and a link to the worker's README
for the full disclosure. Be candid that activity dates are retained for 13
months. Match the existing changelog's level of detail.

- [ ] **Step 3: Document it in the README**

Add a short "Anonymous usage data (optional)" section to the integration's
`README.md`: off by default, what the three toggles do, that the worker is open
source, and a link to its README for the complete disclosure including what
Cloudflare sees.

- [ ] **Step 4: Run the full gate**

```bash
bash scripts/pre-commit-docker-test.sh
```

Expected: `✅ Version: 3.0.44` and everything green.

- [ ] **Step 5: Commit**

```bash
git add custom_components/homgar/manifest.json CHANGELOG.md README.md
git commit -m "chore(release): 3.0.44 — opt-in anonymous telemetry"
```

---

## Done when

- All three telemetry suites pass inside `ha-test` and are wired into the gate.
- The full Docker gate is green with `✅ Version: 3.0.44`.
- With telemetry off (the default), **no request is made** — verified by the
  send tests, and observable as no new rows via the worker's `/stats`.
- With telemetry on, a real ping from the container lands and appears in
  `/stats` (the transport is already proven; this confirms the wiring).
- The opt-in notification appears once in the real UI and never returns once a
  choice is saved.

**Then:** tag `v3.0.44` and cut the release per `docs/releasing.md`, and post to
Discord and the relevant issues as usual.
