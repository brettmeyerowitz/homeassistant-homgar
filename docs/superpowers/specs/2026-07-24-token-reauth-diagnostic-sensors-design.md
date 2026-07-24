# Token re-auth diagnostic sensors — design

- **Date:** 2026-07-24
- **Branch:** `fix/control-token-reauth` (bundled into the v3.0.41 release)
- **Status:** approved, ready for implementation plan

## Problem

After v3.0.40 (User-Agent 403 fix) let requests reach the HomGar cloud again, a
power user (@shaundekok) reported valve control failing with
`controlWorkMode failed: code=1004 msg=token error` and the MQTT renewal loop
stuck on `subscribeStatus failed: {'code': 1001, 'msg': 'NOT_TOKEN'}`, plus an
impression that "the token times out every minute."

The re-auth/retry recovery already committed on this branch converts those hard
failures into silent recovery. But the **"every minute"** claim is unexplained
and not reproducible on the maintainer's own account, where the token is
long-lived (server lifetime ~60 days; one login at boot; 120 s HTTP poll). A
token rejected every ~60 s is therefore not natural expiry — it points to an
*external session invalidating the token* (concurrent phone app, or a duplicate
config entry sharing the deterministic `deviceId`).

We cannot see Shaun's token behaviour directly. We need to **make re-auth
measurable inside any user's Home Assistant** so the rhythm is visible from the
HA history graph, with zero data leaving HA.

## Scope

**In scope (this change):** local, HA-native diagnostic sensors that expose
token re-auth activity. Purely local — no network, no PII, no opt-in.

**Out of scope (deliberate follow-up):** pushing the same telemetry to the
`homeassistant-homgar-debug-worker` Cloudflare Worker. That layer needs an
explicit opt-in and a new worker endpoint, and is only worth building once the
sensors confirm they capture the right signal. Tracked separately.

## Design

### 1. Instrument the single re-auth choke point

All re-authentications funnel through `HomGarClient._reauth()`
(`custom_components/homgar/api/client.py`). Add session-scoped state to the
client (resets on HA restart — acceptable, churn shows within a session):

```python
self._reauth_count = 0            # running total this runtime
self._last_reauth_at = None       # datetime, UTC
self._last_reauth_trigger = None  # endpoint name, e.g. "subscribeStatus"
self._last_reauth_code = None     # 1001 or 1004
```

`_reauth()` gains two optional arguments and updates the state:

```python
async def _reauth(self, trigger: str | None = None, code: int | None = None) -> None:
    self._reauth_count += 1
    self._last_reauth_at = datetime.now(timezone.utc)
    self._last_reauth_trigger = trigger
    self._last_reauth_code = code
    ...  # existing behaviour: clear token, login()
```

All existing `_reauth()` call sites (the 3 read endpoints, the 2 control
endpoints, `subscribeStatus`, `getDeviceStatus`, `setDeviceStatus`,
`productModel`) pass their endpoint name and the rejecting code — both already
in scope at the call site (`data.get("code")`). Example:

```python
if data.get("code") in (1001, 1004):
    await self._reauth(trigger="subscribeStatus", code=data.get("code"))
```

`_token_expires_at` already exists; no change needed for expiry.

Read-only accessors keep the sensor decoupled from client internals, e.g.
`reauth_count`, `last_reauth_at`, `last_reauth_trigger`, `last_reauth_code`,
`token_expires_at` (property or simple getters).

### 2. Three DIAGNOSTIC sensors, one set per config entry, enabled by default

New file `custom_components/homgar/diagnostic_token_sensors.py` (keeps
`sensor.py` focused), wired into `sensor.py:async_setup_entry` beside the
existing `diagnostic_sensors` import. One set per config entry.

| Entity (object_id) | device_class / state_class | Source | Notes |
|---|---|---|---|
| `sensor.homgar_token_reauth_count` | numeric, `state_class=total_increasing` | `reauth_count` | The staircase; slope = churn rate; feeds long-term Statistics |
| `sensor.homgar_last_token_reauth` | `device_class=timestamp` | `last_reauth_at` | attrs: `trigger_endpoint`, `last_error_code` |
| `sensor.homgar_token_expires_at` | `device_class=timestamp` | `token_expires_at` | far-future value ⇒ not natural expiry |

- `entity_category = EntityCategory.DIAGNOSTIC`, `entity_registry_enabled_default = True`.
- `CoordinatorEntity`; `native_value` reads live client state each coordinator
  refresh (120 s). Re-auths triggered by a coordinator *read* surface
  immediately (that refresh finishes and pushes new data); re-auths triggered by
  the independent MQTT renewal surface on the next cycle — up to 120 s lag,
  acceptable for a minute-scale rhythm observed over several minutes.
- Stable `unique_id` per config entry, e.g. `f"{entry_id}_token_reauth_count"`.

### 3. Attach point (device)

Attach to the top-level **Hub** device — the per-home gateway
(`identifiers={(DOMAIN, f"rainpoint_hub_{mid}")}`), the closest thing to an
account-level device. Token state is account-wide, so the Hub is its natural
home. HA renders `DIAGNOSTIC` entities in their own "Diagnostic" card on the Hub
device page. If an entry has multiple hubs, attach to the primary/first hub
(one set per entry, not per hub).

### 4. Where it surfaces (for reviewers)

- **Device page:** Settings → Devices & Services → HomGar/RainPoint → **Hub** →
  Diagnostic card shows the three sensors.
- **Entities tab:** search `token`.
- **History:** open *Token re-auth count* → History graph = the staircase; also
  in long-term Statistics. *Last token re-auth* attributes show the last
  `trigger_endpoint` / `last_error_code`.

### 5. Optional: paste-ready Lovelace card

Include a `history-graph` card snippet (all three sensors) in the PR body /
README so the maintainer and Shaun get the staircase in one view without
clicking around. Documentation only; no code dependency.

## Testing

TDD in the `ha-test` container (Python 3.14), extending the existing
`tests/run_token_reauth_tests.py` style or a new `run_token_diag_tests.py`:

1. `_reauth(trigger, code)` increments `reauth_count`, stamps `last_reauth_at`,
   and records `trigger`/`code`.
2. Multiple re-auths accumulate (count is monotonic within a session).
3. Sensor `native_value` maps correctly for each of the three sensors, including
   the `timestamp` device_class values and the `trigger_endpoint` /
   `last_error_code` attributes.
4. Sensors are enabled-by-default and in the DIAGNOSTIC category.

Wire the suite into `scripts/pre-commit-docker-test.sh`. Full gate must pass;
deploy to `ha-test` and confirm the three entities appear on the Hub device with
sane values and no tracebacks.

## Delivery

- Bundle into the existing `fix/control-token-reauth` branch → **v3.0.41**, so a
  single install gives users both the recovery fix and the visibility.
- CHANGELOG 3.0.41 gains a second bullet under a **Diagnostics** heading
  describing the three sensors and how to read the staircase.
- manifest already at `3.0.41`.

## Risks / notes

- Adds three enabled entities to every user's Hub device. Mitigated by the
  DIAGNOSTIC category (tucked away, not on default dashboards) and their obvious
  debug purpose.
- Session-scoped counter resets on restart; `total_increasing` handles resets
  gracefully in HA history/statistics.
- Up-to-120 s surfacing lag for MQTT-renewal-triggered re-auths; documented,
  acceptable for the diagnostic goal.
