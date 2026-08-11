# Opt-in telemetry — design

- **Date:** 2026-08-11
- **Target release:** v3.0.44
- **Status:** approved, ready for implementation plan

## Problem

The maintainer has no way to know how many people run this integration or where
they are. This is not solvable with existing sources:

- Custom (HACS) integrations do **not** report to Home Assistant's official
  analytics — `analytics.home-assistant.io` covers core integrations only.
- HACS publishes no per-repo install counts. GitHub release download counts are
  useless here: releases carry no uploaded assets and HACS pulls the
  auto-generated source zip, whose downloads are not counted (all read `dl=0`).
- GitHub exposes **zero** geography anywhere — no country breakdown for clones,
  views or downloads.

Best available proxies (2026-08-04): ~107 unique cloners/14d (closest to active
installs, noisy), 508 unique repo viewers/14d, 26 stars, 9 forks. Rough estimate:
**~100–150 active users**.

Knowing the real numbers has concrete engineering value beyond curiosity. During
the issue #84 fix we had to reason from published HA tags to decide whether an
unconditional `UnitOfRatio` import would break users below Core 2026.7. A version
distribution would have answered that directly.

## What users said

Discord poll, closed 2026-08-11 09:41 UTC, **n=8**:

| Option | Votes |
|---|---|
| Both — approx. location + device models | 4 (50%) |
| Location only (country/region) | **0** |
| Device models only (no location) | 3 (38%) |
| Just an anonymous "I am here" count | **0** |
| Nothing — I would opt out | 1 (13%) |

**Reading.** 7/8 would share something; one objector. Device models have the
broadest support (7/8). **Location is the contested axis** — 4/8, with three
people explicitly choosing the option that excludes it. Both "location only" and
"count only" scored zero, so people are not uneasy about the concept in the
abstract; they have a specific reservation, and it is geography.

**Caveats that constrain the design.** n=8 against ~100–150 active users is a
5–8% response rate, and Discord members are the most engaged cohort — likely
*more* privacy-tolerant than the silent majority. Treat 88% as a ceiling, not a
forecast.

**Consequence: no single on/off toggle.** One switch either includes location
(losing the ~38% who explicitly declined it) or drops geography (abandoning half
the goal). The opt-in must be granular.

## Scope

**In scope:** a new dedicated Cloudflare Worker with a D1 database; an opt-in
telemetry client in the integration; granular opt-in UX in the config and options
flows; a one-time prompt for existing installs.

**Out of scope (deliberate YAGNI):** entity counts, per-device data beyond model
names, crash reporting, any dashboard beyond a JSON `/stats`, and gating on Home
Assistant's own analytics preference (see Rejected alternatives).

## Architecture

Three independently testable pieces:

| Component | Responsibility |
|---|---|
| `homgar-telemetry-worker` (new sibling repo) | Receive pings, enforce privacy rules server-side, aggregate into D1 |
| `custom_components/homgar/telemetry.py` (new) | Anon ID, payload construction, daily guard, send |
| `config_flow.py` / `__init__.py` / `const.py` (edits) | Opt-in UX and the one-time prompt |

### Why a new worker rather than extending the existing one

The existing `homgar-debug-worker` collects device payloads for decoder work — a
different purpose with a different privacy promise. It also has two properties
that disqualify it as a host for telemetry:

- **No authentication anywhere.** `/stats` carries a literal
  `// TODO: Add authentication for stats endpoint`; `/view` and `/json` are open
  too. Telemetry aggregates must not sit beside publicly readable endpoints.
- **It logs full request bodies** via `console.log('Received submission:', …)`,
  which would put telemetry pings into Workers Logs.

It also binds only KV, so a D1 binding is new work regardless. The existing
worker is left untouched.

### Why D1 rather than KV

KV was the reflex choice because the debug worker already binds it. It is the
wrong tool here:

- **KV increments are not atomic.** A counter is a read-modify-write, so two
  concurrent pings silently lose an increment. This is a correctness bug, not a
  performance concern.
- KV caps at ~1 write/sec per key.
- KV has no query capability — counting distinct installs means listing every
  key and iterating, and every aggregate must be denormalised into hand-maintained
  counters that can drift out of sync.

D1 gives atomic `UPSERT`, real aggregation (`GROUP BY`), one-line retention
purges, and aggregates computed on read so nothing can drift. The workload —
~150 writes/day — sits far inside the free tier (100k row writes/day).

## Data model

```sql
CREATE TABLE installs (
  anon_id             TEXT PRIMARY KEY,  -- random UUID4, no link to any account
  integration_version TEXT NOT NULL,
  hass_version        TEXT NOT NULL,
  first_seen          INTEGER NOT NULL,
  last_seen           INTEGER NOT NULL,
  last_counted_month  TEXT               -- "2026-08", gates monthly aggregation
);

CREATE TABLE country_counts (
  country TEXT, month TEXT, count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (country, month)
);

CREATE TABLE model_counts (
  model TEXT, month TEXT, count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (model, month)
);
```

Country and device models are both **aggregate-only**. No foreign key and no
query path joins either back to an `anon_id`, so "we never store your location
against your install" is true by construction rather than by policy. Models get
the same treatment because it costs nothing.

`last_counted_month` gates both aggregates. **Known edge case, documented rather
than engineered around:** enabling country partway through a month means being
counted from the following month.

Derived figures:

- **Active installs** — `COUNT(*) FROM installs WHERE last_seen > now-30d`
- **Version adoption** — `GROUP BY integration_version` / `hass_version`
- **Geography** — `country_counts` for the month
- **Retention** — rows unseen for 90 days are purged

## Data flow

The client sends the flags; the worker branches on them.

```json
POST /ping
{
  "anon_id": "…",
  "integration_version": "3.0.44",
  "hass_version": "2026.8.1",
  "share_country": true,
  "share_models": true,
  "models": ["HTV245FRF", "HWG023WBRF-V2"]
}
```

`models` is **omitted entirely** when not opted in — not sent and ignored. The
worker upserts `installs`, then if `last_counted_month` differs from the current
month, increments `country_counts` (only when `share_country`) and `model_counts`
(only when `share_models`), and stamps the month. Returns `204` with no body.

### Endpoints

| Route | Access | Behaviour |
|---|---|---|
| `POST /ping` | public, write-only | Accepts a payload, returns 204, echoes nothing |
| `GET /stats` | bearer token (Wrangler secret) | JSON aggregates |
| `GET /health` | public | Liveness only |

## Privacy enforcement

The Worker can always see the visitor's IP and `request.cf.country` — that is
true of any HTTP request to any server. What makes the "no location" toggle
meaningful is that reading and persisting it is our choice, enforced server-side
and verifiable because the Worker is open source. Six rules:

1. `request.cf.country` is read **only inside** the `share_country` branch.
2. `cf.colo`, `cf.region`, `cf.city`, `cf.timezone`, `cf.latitude` and
   `cf.longitude` are **never** read. Each is an indirect location leak — storing
   `cf.colo` while skipping `country` would be an accidental lie.
3. No `console.log` of bodies or headers. `CF-Connecting-IP` is never touched.
   Workers observability is disabled in `wrangler.toml` so nothing reaches Logs.
4. No schema column can hold an IP, so it cannot be stored by accident.
5. `/stats` requires a bearer token; `/ping` is write-only and returns nothing
   readable.
6. The Worker README states the schema verbatim and says plainly: *Cloudflare
   terminates the connection and therefore sees your IP address, as any web
   server does — we never read, log, or store it.* The same disclosure appears in
   the opt-in notification text, including that the HA and integration versions
   are part of the base payload.

## Opt-in UX

A master switch plus two sub-toggles, all defaulting to off:

```
[ ] Share anonymous usage data
      └ [ ] Include my country
      └ [ ] Include device models
```

Added to the existing `HomGarOptionsFlow` (which already carries two settings) and
as a step in the config flow for new installs.

**Reaching existing installs.** A config-flow change reaches new installs only,
and an options flow is pull-only. Existing installs therefore get a single
`persistent_notification` (id `homgar_telemetry_optin`) when `telemetry_choice` is
unset, linking to the Configure page. Saving any choice — including "no" — sets
`telemetry_choice` and clears the notification, so it never returns.

This follows the codebase's established pattern (five existing notifications with
stable IDs). A Repairs issue would allow a one-click inline answer and would
likely convert better, but Repairs is framed as "something needs fixing", and
using it to solicit data collection reads as a dark pattern to a
privacy-sensitive audience.

**Honest ceiling:** opt-in reach is new installs + reconfigurers + the responsive
subset of existing users. Never 100%, and realistically well under the poll's
88%. Sufficient for a rough count and distribution, which is the goal.

## Scheduling

The ping piggybacks on the existing coordinator cycle (120s) behind a 24h guard:
if telemetry is enabled and more than a day has passed, send one. No new timer to
cancel on unload and no second failure path, for what is one HTTP POST per day.

**Persistence (explicit, to avoid ambiguity in implementation):**

| Value | Stored in | Why |
|---|---|---|
| `anon_id` | config entry **data** | Must survive restarts and options edits; not user-editable |
| `telemetry_choice`, `share_country`, `share_models` | config entry **options** | User-editable via the options flow |
| `last_ping_at` | config entry **data** | Must survive restarts, or a frequently-restarted instance re-pings on every boot |

Rejected: a dedicated `async_track_time_interval` (ceremony for one daily
request), and ping-on-setup-only (it would measure *restarts* rather than usage,
systematically undercounting the most stable installs — the opposite of what is
wanted).

## Error handling

Telemetry must never affect integration operation. The entire send is wrapped;
failures log at debug and are swallowed. 10s timeout, no retries — a missed daily
ping is not worth chasing. It runs inside the coordinator cycle but cannot raise
into it.

## Testing

Per repo convention, standalone runners in the `ha-test` container, wired into
`scripts/pre-commit-docker-test.sh`.

**Integration side:**

- anon ID is generated once and persists across restarts
- payload omits `models` entirely when models are not opted in
- **payload contains no location field under any toggle combination**
- no ping at all when the master switch is off
- daily guard holds within 24h and releases after
- a send failure never raises into the coordinator
- notification fires once when `telemetry_choice` is unset, and not when it is set

**Worker side (vitest):**

- country is stored only when `share_country` is true
- `cf.colo`, `cf.city`, `cf.timezone` are never read — asserted against a mock
  `cf` object carrying all of them
- monthly dedupe: a second ping in the same month does not double-count
- `/stats` rejects requests without a valid token
- `/ping` returns 204 and no body

## Build order

Two deliverables in two repos. They are separable and should be built in this
order, since the second is untestable end to end without the first:

1. **Worker** (`homgar-telemetry-worker`) — schema, `/ping`, `/stats`, `/health`,
   privacy rules, vitest suite, deployed. Verifiable standalone with `curl`.
2. **Integration** (`v3.0.44`) — `telemetry.py`, opt-in UX, one-time
   notification, standalone test runners, wired into the Docker gate.

Only step 2 ships to users; step 1 can be deployed and exercised first without
any user-visible change.

## Rejected alternatives

**Gating the prompt on Home Assistant's own analytics preference.** Appealing as
a trust signal, but it requires reading another integration's internal store,
which is fragile and would break silently on a core refactor. An explicit,
off-by-default opt-in is the stronger consent story regardless.

**One anon ID per HA instance.** The ID is per config entry, so a user with two
accounts counts as two installs. Rare enough to document rather than solve.

## Open risks

- **Sample bias.** Every figure this produces is drawn from the subset who opted
  in, which skews toward engaged, privacy-tolerant users. Treat outputs as
  directional, never as a census.
- **The month-boundary edge case** in `last_counted_month` (above).
