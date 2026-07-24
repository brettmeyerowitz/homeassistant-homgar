# Token re-auth diagnostic sensors — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose token re-authentication activity as three enabled, local-only HA diagnostic sensors on the Hub device so the "token times out every minute" question is answerable from the history graph.

**Architecture:** Instrument the single `HomGarClient._reauth()` choke point with session-scoped counters/timestamps and read-only accessors. Add a focused `diagnostic_token_sensors.py` with three `CoordinatorEntity` sensors that read that client state and attach to the Hub device, wired into `sensor.py:async_setup_entry` once per config entry.

**Tech Stack:** Python 3 (HA custom integration), aiohttp client, Home Assistant `SensorEntity`/`CoordinatorEntity`. Tests are standalone `tests/run_*.py` scripts executed in the `ha-test` Docker container (Python 3.14).

## Global Constraints

- Sensors are **local-only**: no network calls, no PII, no opt-in. (Worker telemetry is a separate future change.)
- Sensors are **DIAGNOSTIC** category and **enabled by default**.
- Re-auth counter is **session-scoped** (resets on HA restart).
- Attach to the **Hub** device: `identifiers={(DOMAIN, f"rainpoint_hub_{mid}")}`.
- Bundle into the existing `fix/control-token-reauth` branch → **v3.0.41** (manifest already `3.0.41`).
- No Claude attribution in commits/PRs.
- `_reauth()` signature stays backward-compatible: new args are optional keyword args with defaults.
- Tests run in the container: `docker cp` the repo tree to `/tmp/repo` (clean-remove first, docker cp nests on an existing dir) or rely on the pre-commit gate's `/config` deploy; import integration modules via `sys.path.insert(0, '/config')`.

---

### Task 1: Instrument `_reauth()` with telemetry state + accessors

**Files:**
- Modify: `custom_components/homgar/api/client.py` (add state in `__init__`, params + body in `_reauth`, accessor properties, update 9 call sites)
- Test: `tests/run_token_diag_tests.py` (create)

**Interfaces:**
- Produces (on `HomGarClient`):
  - `_reauth(self, trigger: str | None = None, code: int | None = None) -> None`
  - `reauth_count: int` (property) — session total, starts at 0
  - `last_reauth_at: datetime | None` (property) — UTC aware
  - `last_reauth_trigger: str | None` (property)
  - `last_reauth_code: int | None` (property)
  - `token_expires_at: datetime | None` (property) — exposes existing `_token_expires_at`

- [ ] **Step 1: Write the failing test**

Create `tests/run_token_diag_tests.py`:

```python
"""Regression tests: HomGarClient exposes token re-auth telemetry.

The three diagnostic sensors (added in v3.0.41) read this state. We pin that
_reauth() increments a session counter and records when/what triggered it, and
that the read-only accessors reflect it. See the token-reauth diagnostic spec.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _find_repo_root() -> Path:
    candidates = [Path(__file__).resolve().parent, Path.cwd(), Path("/config")]
    for start in candidates:
        current = start
        while True:
            if (current / "custom_components" / "homgar" / "api" / "client.py").exists():
                return current
            if current.parent == current:
                break
            current = current.parent
    raise RuntimeError("Could not locate repository root containing custom_components/homgar")


ROOT = _find_repo_root()


def _load_module(module_name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _ClientTimeout:
    def __init__(self, total=None, connect=None, sock_connect=None, sock_read=None):
        self.total = total


_aiohttp_stub = types.ModuleType("aiohttp")
_aiohttp_stub.ClientTimeout = _ClientTimeout
_aiohttp_stub.ClientSession = type("ClientSession", (), {})
_aiohttp_stub.ClientError = type("ClientError", (Exception,), {})
sys.modules["aiohttp"] = _aiohttp_stub

sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
sys.modules.setdefault("custom_components.homgar", types.ModuleType("custom_components.homgar"))
sys.modules.setdefault("custom_components.homgar.api", types.ModuleType("custom_components.homgar.api"))
_load_module("custom_components.homgar.const", "custom_components/homgar/const.py")
client_mod = _load_module("custom_components.homgar.api.client", "custom_components/homgar/api/client.py")


PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        print(f"  ✅ {name}")
        PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}")
        FAIL += 1


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return ""


_LOGIN_PAYLOAD = {
    "code": 0, "ts": 1700000000000,
    "data": {"token": "fresh", "refreshToken": "r", "tokenExpired": 3600, "user": {}},
}


class _SequencedSession:
    def __init__(self, queues):
        self._queues = {u: list(p) for u, p in queues.items()}

    def _next(self, url):
        if url.endswith("/auth/basic/app/login"):
            return _FakeResp(_LOGIN_PAYLOAD)
        for key, queue in self._queues.items():
            if url.endswith(key) and queue:
                return _FakeResp(queue.pop(0))
        raise AssertionError(f"No queued response for {url}")

    def post(self, url, **kwargs):
        return self._next(url)

    def get(self, url, **kwargs):
        return self._next(url)


def _make_client(queues):
    session = _SequencedSession(queues)
    client = client_mod.HomGarClient("31", "a@b.com", "pw", session, "homgar")
    client._token = "stale"
    client._refresh_token = "stale-r"
    client._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return client


def _test_initial_state():
    client = _make_client({})
    check("reauth_count starts at 0", client.reauth_count == 0, f"got {client.reauth_count}")
    check("last_reauth_at starts None", client.last_reauth_at is None)
    check("last_reauth_trigger starts None", client.last_reauth_trigger is None)
    check("last_reauth_code starts None", client.last_reauth_code is None)
    check("token_expires_at accessor works", client.token_expires_at is not None)


async def _test_reauth_records_telemetry():
    # subscribe_status hits 1001 then recovers -> one reauth recorded.
    ok = {"code": 0, "data": {"deviceName": "x"}}
    client = _make_client({"/app/device/subscribeStatus": [{"code": 1001, "msg": "NOT_TOKEN"}, ok]})
    await client.subscribe_status(hid=1, hubs=[{"deviceName": "d", "mid": 1, "productKey": "p", "hid": 1}])
    check("reauth_count == 1 after one rejection", client.reauth_count == 1, f"got {client.reauth_count}")
    check("last_reauth_at is set", client.last_reauth_at is not None)
    check("trigger recorded as subscribeStatus", client.last_reauth_trigger == "subscribeStatus",
          f"got {client.last_reauth_trigger!r}")
    check("code recorded as 1001", client.last_reauth_code == 1001, f"got {client.last_reauth_code}")


async def _test_reauth_count_is_monotonic():
    client = _make_client({})
    await client._reauth(trigger="controlWorkMode", code=1004)
    await client._reauth(trigger="getDeviceStatus", code=1004)
    check("reauth_count increments to 2", client.reauth_count == 2, f"got {client.reauth_count}")
    check("latest trigger wins", client.last_reauth_trigger == "getDeviceStatus",
          f"got {client.last_reauth_trigger!r}")


def main() -> int:
    print("Token diagnostic telemetry tests")
    _test_initial_state()
    asyncio.run(_test_reauth_records_telemetry())
    asyncio.run(_test_reauth_count_is_monotonic())
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker exec ha-test rm -rf /tmp/repo && docker exec ha-test mkdir -p /tmp/repo
docker cp custom_components ha-test:/tmp/repo/custom_components >/dev/null
docker cp tests ha-test:/tmp/repo/tests >/dev/null
docker exec ha-test python3 /tmp/repo/tests/run_token_diag_tests.py
```
Expected: FAIL — `AttributeError: 'HomGarClient' object has no attribute 'reauth_count'` (accessor not defined yet).

- [ ] **Step 3: Add telemetry state to `__init__`**

In `custom_components/homgar/api/client.py`, in `HomGarClient.__init__`, after the existing token-state lines (`self._token: str | None = None` … `self._mqtt_credentials: dict = {}`), add:

```python
        # Session-scoped token re-auth telemetry (exposed via diagnostic sensors).
        self._reauth_count = 0
        self._last_reauth_at: datetime | None = None
        self._last_reauth_trigger: str | None = None
        self._last_reauth_code: int | None = None
```

- [ ] **Step 4: Update `_reauth()` to accept and record telemetry**

Replace the `_reauth` method body:

```python
    async def _reauth(self, trigger: str | None = None, code: int | None = None) -> None:
        """Force a fresh login, invalidating the current token."""
        self._reauth_count += 1
        self._last_reauth_at = datetime.now(timezone.utc)
        self._last_reauth_trigger = trigger
        self._last_reauth_code = code
        _LOGGER.info(
            "HomGar: token rejected by server (trigger=%s code=%s), forcing fresh login (reauth #%d)",
            trigger, code, self._reauth_count,
        )
        self._token = None
        self._token_expires_at = None
        if not await self.login():
            raise HomGarApiError("Re-authentication failed")
```

- [ ] **Step 5: Add read-only accessor properties**

Immediately after `_reauth`, add:

```python
    @property
    def reauth_count(self) -> int:
        return self._reauth_count

    @property
    def last_reauth_at(self) -> datetime | None:
        return self._last_reauth_at

    @property
    def last_reauth_trigger(self) -> str | None:
        return self._last_reauth_trigger

    @property
    def last_reauth_code(self) -> int | None:
        return self._last_reauth_code

    @property
    def token_expires_at(self) -> datetime | None:
        return self._token_expires_at
```

- [ ] **Step 6: Pass trigger/code at all 9 call sites**

For each endpoint, change its `await self._reauth()` to pass the endpoint label and the rejecting code. The preceding line is always `if data.get("code") in (1001, 1004):`. Make these exact replacements:

| Method | New call |
|---|---|
| `list_homes` | `await self._reauth(trigger="list_homes", code=data.get("code"))` |
| `get_devices_by_hid` | `await self._reauth(trigger="getDeviceByHid", code=data.get("code"))` |
| `get_multiple_device_status` | `await self._reauth(trigger="multipleDeviceStatus", code=data.get("code"))` |
| `get_device_status` | `await self._reauth(trigger="getDeviceStatus", code=data.get("code"))` |
| `subscribe_status` | `await self._reauth(trigger="subscribeStatus", code=data.get("code"))` |
| `set_device_state` | `await self._reauth(trigger="setDeviceStatus", code=data.get("code"))` |
| `get_product_models` | `await self._reauth(trigger="productModel", code=data.get("code"))` |
| `control_work_mode` | `await self._reauth(trigger="controlWorkMode", code=data.get("code"))` |
| `control_work_mode_dp` | `await self._reauth(trigger="controlWorkModeDP", code=data.get("code"))` |

(9 occurrences of `await self._reauth()` → the labeled form. Verify none remain: `grep -n "self._reauth()" custom_components/homgar/api/client.py` returns nothing.)

- [ ] **Step 7: Run diag test to verify it passes**

```bash
docker exec ha-test rm -rf /tmp/repo/custom_components && docker cp custom_components ha-test:/tmp/repo/custom_components >/dev/null
docker exec ha-test python3 /tmp/repo/tests/run_token_diag_tests.py
```
Expected: PASS — `12 passed, 0 failed`.

- [ ] **Step 8: Run the existing token-reauth suite to confirm no regression**

```bash
docker cp tests ha-test:/tmp/repo/tests >/dev/null
docker exec ha-test python3 /tmp/repo/tests/run_token_reauth_tests.py
```
Expected: PASS — `23 passed, 0 failed` (defaulted args keep old behaviour).

- [ ] **Step 9: Commit**

```bash
git add custom_components/homgar/api/client.py tests/run_token_diag_tests.py
git commit -m "feat(api): record session token re-auth telemetry on _reauth()"
```

---

### Task 2: Add the three Hub diagnostic sensors

**Files:**
- Create: `custom_components/homgar/diagnostic_token_sensors.py`
- Test: `tests/run_token_sensor_tests.py` (create — runs in-container, imports HA via `/config`)

**Interfaces:**
- Consumes (from Task 1): `client.reauth_count`, `client.last_reauth_at`, `client.last_reauth_trigger`, `client.last_reauth_code`, `client.token_expires_at`; `coordinator._client`.
- Produces:
  - `HomGarTokenReauthCountSensor(coordinator, hub_info, entry_id)`
  - `HomGarLastTokenReauthSensor(coordinator, hub_info, entry_id)`
  - `HomGarTokenExpiresAtSensor(coordinator, hub_info, entry_id)`
  - `build_token_diagnostic_sensors(coordinator, hub_info, entry_id) -> list` (factory used by `sensor.py`)

- [ ] **Step 1: Write the failing test**

Create `tests/run_token_sensor_tests.py` (runs inside the container where `homeassistant` is importable):

```python
"""Token diagnostic sensor tests. Runs in the ha-test container against the
deployed integration at /config (imports Home Assistant)."""
import sys
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/config")

from custom_components.homgar.diagnostic_token_sensors import (  # noqa: E402
    HomGarTokenReauthCountSensor,
    HomGarLastTokenReauthSensor,
    HomGarTokenExpiresAtSensor,
    build_token_diagnostic_sensors,
)
from homeassistant.components.sensor import SensorStateClass, SensorDeviceClass  # noqa: E402
from homeassistant.const import EntityCategory  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


now = datetime.now(timezone.utc)
expires = now + timedelta(days=38)
client = types.SimpleNamespace(
    reauth_count=7,
    last_reauth_at=now,
    last_reauth_trigger="subscribeStatus",
    last_reauth_code=1001,
    token_expires_at=expires,
)
coordinator = types.SimpleNamespace(_client=client, data={"hubs": []}, last_update_success=True)
hub_info = {"mid": 12345, "name": "Hub", "model": "HWG023WBRF-V2"}
ENTRY = "entry_abc"

count = HomGarTokenReauthCountSensor(coordinator, hub_info, ENTRY)
last = HomGarLastTokenReauthSensor(coordinator, hub_info, ENTRY)
exp = HomGarTokenExpiresAtSensor(coordinator, hub_info, ENTRY)

check("count native_value reads reauth_count", count.native_value == 7, f"got {count.native_value}")
check("count is total_increasing", count.state_class == SensorStateClass.TOTAL_INCREASING)
check("count is DIAGNOSTIC", count.entity_category == EntityCategory.DIAGNOSTIC)
check("count enabled by default", count.entity_registry_enabled_default is True)
check("count unique_id is entry-scoped",
      count.unique_id == f"{ENTRY}_token_reauth_count", f"got {count.unique_id}")
check("count attaches to hub device",
      (DOMAIN_ID := ("homgar", f"rainpoint_hub_12345")) in count.device_info["identifiers"])

check("last native_value is the reauth timestamp", last.native_value == now)
check("last is timestamp device_class", last.device_class == SensorDeviceClass.TIMESTAMP)
check("last exposes trigger attr",
      last.extra_state_attributes.get("trigger_endpoint") == "subscribeStatus")
check("last exposes error code attr",
      last.extra_state_attributes.get("last_error_code") == 1001)

check("expires native_value is token_expires_at", exp.native_value == expires)
check("expires is timestamp device_class", exp.device_class == SensorDeviceClass.TIMESTAMP)

built = build_token_diagnostic_sensors(coordinator, hub_info, ENTRY)
check("factory returns exactly 3 sensors", len(built) == 3, f"got {len(built)}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker cp tests/run_token_sensor_tests.py ha-test:/tmp/run_token_sensor_tests.py >/dev/null
docker exec ha-test python3 /tmp/run_token_sensor_tests.py
```
Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.homgar.diagnostic_token_sensors'`.

- [ ] **Step 3: Create the sensor module**

Create `custom_components/homgar/diagnostic_token_sensors.py`:

```python
"""Token re-auth diagnostic sensors (v3.0.41).

Three local-only DIAGNOSTIC sensors on the Hub device that expose the client's
session token re-auth telemetry, so a token being rejected repeatedly (e.g. a
concurrent-session war) is visible from the HA history graph. No network, no
PII. See docs/superpowers/specs/2026-07-24-token-reauth-diagnostic-sensors-design.md.
"""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomGarCoordinator


class _HomGarTokenSensorBase(CoordinatorEntity, SensorEntity):
    """Base for the account-level token diagnostic sensors (one set per entry)."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = True
    _attr_has_entity_name = True

    def __init__(self, coordinator: HomGarCoordinator, hub_info: dict, entry_id: str) -> None:
        super().__init__(coordinator)
        self._hub_info = hub_info
        self._entry_id = entry_id

    @property
    def _client(self):
        return self.coordinator._client

    @property
    def available(self) -> bool:
        return self.coordinator._client is not None

    @property
    def device_info(self) -> DeviceInfo:
        mid = self._hub_info["mid"]
        return DeviceInfo(identifiers={(DOMAIN, f"rainpoint_hub_{mid}")})


class HomGarTokenReauthCountSensor(_HomGarTokenSensorBase):
    """Number of token re-authentications since HA (re)started."""

    _attr_icon = "mdi:counter"
    _attr_name = "Token re-auth count"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, hub_info, entry_id):
        super().__init__(coordinator, hub_info, entry_id)
        self._attr_unique_id = f"{entry_id}_token_reauth_count"

    @property
    def native_value(self) -> int:
        return self._client.reauth_count


class HomGarLastTokenReauthSensor(_HomGarTokenSensorBase):
    """Timestamp of the most recent token re-authentication."""

    _attr_icon = "mdi:key-alert"
    _attr_name = "Last token re-auth"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, hub_info, entry_id):
        super().__init__(coordinator, hub_info, entry_id)
        self._attr_unique_id = f"{entry_id}_last_token_reauth"

    @property
    def native_value(self) -> datetime | None:
        return self._client.last_reauth_at

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "trigger_endpoint": self._client.last_reauth_trigger,
            "last_error_code": self._client.last_reauth_code,
        }


class HomGarTokenExpiresAtSensor(_HomGarTokenSensorBase):
    """When the current token expires (far future => not natural expiry)."""

    _attr_icon = "mdi:clock-end"
    _attr_name = "Token expires at"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, hub_info, entry_id):
        super().__init__(coordinator, hub_info, entry_id)
        self._attr_unique_id = f"{entry_id}_token_expires_at"

    @property
    def native_value(self) -> datetime | None:
        return self._client.token_expires_at


def build_token_diagnostic_sensors(
    coordinator: HomGarCoordinator, hub_info: dict, entry_id: str
) -> list[_HomGarTokenSensorBase]:
    """Build the one-per-entry token diagnostic sensor set."""
    return [
        HomGarTokenReauthCountSensor(coordinator, hub_info, entry_id),
        HomGarLastTokenReauthSensor(coordinator, hub_info, entry_id),
        HomGarTokenExpiresAtSensor(coordinator, hub_info, entry_id),
    ]
```

- [ ] **Step 4: Fix the test's DOMAIN reference and re-run**

The test references `("homgar", ...)`; the real domain constant is `DOMAIN` from const. Add near the top of `tests/run_token_sensor_tests.py` (after the `sys.path.insert`):

```python
from custom_components.homgar.const import DOMAIN  # noqa: E402
```

and change the `count attaches to hub device` check to:

```python
check("count attaches to hub device",
      (DOMAIN, f"rainpoint_hub_12345") in count.device_info["identifiers"])
```

Then redeploy the integration to `/config` and run:

```bash
docker cp custom_components/homgar ha-test:/config/custom_components/ >/dev/null
docker cp tests/run_token_sensor_tests.py ha-test:/tmp/run_token_sensor_tests.py >/dev/null
docker exec ha-test python3 /tmp/run_token_sensor_tests.py
```
Expected: PASS — `15 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add custom_components/homgar/diagnostic_token_sensors.py tests/run_token_sensor_tests.py
git commit -m "feat(sensor): add token re-auth diagnostic sensors on the Hub device"
```

---

### Task 3: Wire into setup, gate, changelog; deploy & verify

**Files:**
- Modify: `custom_components/homgar/sensor.py` (import + create one set per entry in `async_setup_entry`)
- Modify: `scripts/pre-commit-docker-test.sh` (run the two new suites)
- Modify: `CHANGELOG.md` (Diagnostics bullet + Lovelace card)

**Interfaces:**
- Consumes (from Task 2): `build_token_diagnostic_sensors(coordinator, hub_info, entry_id)`.

- [ ] **Step 1: Import the factory in `sensor.py`**

In `custom_components/homgar/sensor.py`, after the `from .diagnostic_sensors import (...)` block (ends line ~36), add:

```python
from .diagnostic_token_sensors import build_token_diagnostic_sensors
```

- [ ] **Step 2: Create the sensors once per entry (on the first hub)**

In `async_setup_entry`, immediately after the `for hub_key, hub_info in hubs_dict.items():` loop that adds hub sensors (right before the `# Create sensor entities for sub-devices` comment, ~line 112), add:

```python
    # Account-level token diagnostic sensors: one set per config entry, attached
    # to the first hub's device. Guarded so entries with no hub add nothing.
    if hubs_dict:
        first_hub_info = next(iter(hubs_dict.values()))
        entities.extend(
            build_token_diagnostic_sensors(coordinator, first_hub_info, entry.entry_id)
        )
```

- [ ] **Step 3: Add both suites to the pre-commit gate**

In `scripts/pre-commit-docker-test.sh`, after the existing "token re-auth regression tests" block (ends with `fi` after the `run_token_reauth_tests.py` block), insert:

```bash
# ── Test: token telemetry + sensor regressions ────────────────────────────
echo "🧪 Running token telemetry tests..."
docker cp tests/run_token_diag_tests.py ha-test:/tmp/tests/run_token_diag_tests.py > /dev/null
if docker exec ha-test python3 /tmp/tests/run_token_diag_tests.py; then
    echo "✅ Token telemetry tests passed"
else
    echo "❌ ERROR: Token telemetry tests failed"
    exit 1
fi

echo "🧪 Running token diagnostic sensor tests..."
docker cp tests/run_token_sensor_tests.py ha-test:/tmp/run_token_sensor_tests.py > /dev/null
if docker exec ha-test python3 /tmp/run_token_sensor_tests.py; then
    echo "✅ Token diagnostic sensor tests passed"
else
    echo "❌ ERROR: Token diagnostic sensor tests failed"
    exit 1
fi
```

- [ ] **Step 4: Run the full pre-commit gate**

```bash
bash scripts/pre-commit-docker-test.sh 2>&1 | tail -n 30
```
Expected: `🎉 All pre-commit tests passed! Commit allowed.` The gate deploys the tree to `/config` and restarts HA.

- [ ] **Step 5: Verify the three entities exist on the Hub with sane values**

```bash
docker exec ha-test sh -c 'python3 - <<"PY"
import json
d = json.load(open("/config/.storage/core.entity_registry"))
toks = [e for e in d["data"]["entities"]
        if e["platform"] == "homgar" and "token" in e["entity_id"]]
for e in toks:
    print(e["entity_id"], "| disabled_by:", e.get("disabled_by"), "| unique:", e["unique_id"])
print("count:", len(toks))
PY'
```
Expected: three rows — `sensor.*_token_reauth_count`, `*_last_token_reauth`, `*_token_expires_at` — all `disabled_by: None`. Also confirm no tracebacks:
```bash
docker exec ha-test sh -c 'grep -c Traceback /config/home-assistant.log'
```
Expected: `0`.

- [ ] **Step 6: Add the Diagnostics changelog bullet + Lovelace card**

In `CHANGELOG.md`, under the existing `## [3.0.41] - 2026-07-24` section, add a new subsection after the `### 🧪 Tests` block for that version:

```markdown
### 🔎 Diagnostics
- **Token re-auth visibility** — three local-only diagnostic sensors on the Hub device make token re-authentication measurable: `Token re-auth count` (a `total_increasing` value whose history-graph slope shows how often the cloud is rejecting the token), `Last token re-auth` (timestamp, with `trigger_endpoint` and `last_error_code` attributes), and `Token expires at` (a far-future value here means the token is long-lived and any churn is external session invalidation, not expiry). Enabled by default, no data leaves Home Assistant. Find them under Settings → Devices & Services → HomGar/RainPoint → Hub → Diagnostic. To watch the rhythm on one graph:

    ```yaml
    type: history-graph
    hours_to_show: 6
    entities:
      - sensor.homgar_token_reauth_count
      - sensor.homgar_last_token_reauth
      - sensor.homgar_token_expires_at
    ```
```

- [ ] **Step 7: Commit**

```bash
git add custom_components/homgar/sensor.py scripts/pre-commit-docker-test.sh CHANGELOG.md
git commit -m "feat(sensor): wire token diagnostic sensors into setup + gate + changelog"
```

---

## Self-Review

**Spec coverage:**
- Instrument `_reauth()` choke point (spec §1) → Task 1. ✓
- Session-scoped state + accessors (spec §1) → Task 1 Steps 3–5. ✓
- 9 call sites pass trigger + code (spec §1) → Task 1 Step 6. ✓
- Three DIAGNOSTIC sensors, enabled by default, correct classes (spec §2) → Task 2. ✓
- Attach to Hub device `rainpoint_hub_{mid}` (spec §3) → Task 2 `device_info`. ✓
- One set per config entry, first hub, guarded (spec §2/§3) → Task 3 Step 2. ✓
- TDD in container + pre-commit gate (spec Testing) → Tasks 1–3, gate in Task 3 Step 3–4. ✓
- Deploy to ha-test, entities render, no tracebacks (spec Testing) → Task 3 Step 5. ✓
- Bundle into v3.0.41, Diagnostics changelog bullet, Lovelace card (spec Delivery/§5) → Task 3 Step 6. ✓
- Local-only, no telemetry push (spec Scope) → no network code added. ✓

**Placeholder scan:** none — all steps carry exact code/commands.

**Type consistency:** `_reauth(trigger, code)`, `reauth_count`, `last_reauth_at`, `last_reauth_trigger`, `last_reauth_code`, `token_expires_at`, `build_token_diagnostic_sensors(coordinator, hub_info, entry_id)`, and the three sensor class names are used identically across Tasks 1–3. ✓

**Note on test counts:** "12/15 passed" figures are the sum of `check()` calls in each suite; if you add/remove a check, update the expected line accordingly.
