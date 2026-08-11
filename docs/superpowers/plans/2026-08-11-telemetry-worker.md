# Telemetry Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy `homgar-telemetry-worker` — a Cloudflare Worker with a D1 database that receives anonymous opt-in pings from the HomGar integration, enforces the privacy rules server-side, and exposes authenticated aggregates.

**Architecture:** A single-file Worker routing four endpoints against a D1 database. `installs` is the identifier dimension, `pings` is a date-only fact table keyed `(anon_id, day)`, and `country_counts`/`model_counts` are aggregate-only tables with no join path back to an install. The client sends opt-in flags; the Worker branches on them and reads `request.cf.country` only when location is opted in.

**Tech Stack:** Cloudflare Workers (ES modules), D1 (SQLite), Wrangler 4.x, Vitest with `@cloudflare/vitest-pool-workers` (real workerd runtime + real D1 bindings in tests).

**Spec:** `docs/superpowers/specs/2026-08-11-optin-telemetry-design.md`

## Global Constraints

- **This repo is `/Users/brett/Code/homgar-telemetry-worker` — a NEW repo, sibling to `homeassistant-homgar`.** Do not modify `homgar-telemetry-worker`'s neighbour `homgar-debug-worker` in any way.
- **No request body, header, or IP may ever be logged.** No `console.log` of `body`, `request.headers`, or `CF-Connecting-IP`. `[observability] enabled = false` in `wrangler.toml`.
- **`request.cf.country` is the ONLY `cf` field that may be read**, and only inside a `share_country === true` branch. `city`, `region`, `regionCode`, `postalCode`, `latitude`, `longitude`, `timezone`, `colo`, `asn`, `asOrganization` must never appear in the source.
- **`day` and `month` are always derived from the Worker's clock, never from client input.** A payload carrying its own `day`/`ts`/`month` must be ignored.
- **Country and device models are aggregate-only.** No column linking either to `anon_id` may be added to any table.
- **Secrets go in `wrangler secret put`, never `[vars]`.** (The neighbouring debug worker commits `JWT_SECRET = "your-jwt-secret-here"` to `wrangler.toml` — do not copy that pattern.)
- **Date format is `YYYY-MM-DD` everywhere; month format is `YYYY-MM`.** No timestamps, ever.
- Retention: `pings` older than **395 days**; `installs` with `last_seen` older than **90 days**.

---

### Task 1: Repo scaffold and edge probe (spec step 0)

The spec's field table is unverified. `request.cf` is not populated by `wrangler dev` locally, so the only way to know what the deployed edge actually exposes is to deploy and look. Everything the README claims depends on this.

**Files:**
- Create: `/Users/brett/Code/homgar-telemetry-worker/package.json`
- Create: `/Users/brett/Code/homgar-telemetry-worker/wrangler.toml`
- Create: `/Users/brett/Code/homgar-telemetry-worker/src/index.js`
- Create: `/Users/brett/Code/homgar-telemetry-worker/.gitignore`
- Modify: `/Users/brett/Code/homeassistant-homgar/docs/superpowers/specs/2026-08-11-optin-telemetry-design.md` (the field table)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: a deployed worker at `homgar-telemetry-worker.<subdomain>.workers.dev` with a temporary `GET /__probe` route. Task 7 removes that route.

- [ ] **Step 1: Create the repo and scaffold**

```bash
mkdir -p /Users/brett/Code/homgar-telemetry-worker/src
cd /Users/brett/Code/homgar-telemetry-worker
git init
```

`package.json`:

```json
{
  "name": "homgar-telemetry-worker",
  "version": "1.0.0",
  "description": "Opt-in anonymous telemetry for the HomGar/RainPoint Home Assistant integration",
  "main": "src/index.js",
  "type": "module",
  "scripts": {
    "dev": "wrangler dev",
    "deploy": "wrangler deploy",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "author": "Brett Meyerowitz",
  "license": "MIT",
  "devDependencies": {
    "@cloudflare/vitest-pool-workers": "^0.5.0",
    "vitest": "~2.0.0",
    "wrangler": "^4.78.0"
  }
}
```

`.gitignore`:

```
node_modules/
.wrangler/
.dev.vars
```

`wrangler.toml` (the `database_id` is filled in by Task 2 — leave the D1 block out entirely for now):

```toml
name = "homgar-telemetry-worker"
main = "src/index.js"
compatibility_date = "2026-08-11"

# Never log request bodies, headers, or IPs. See spec: Privacy enforcement.
[observability]
enabled = false
```

- [ ] **Step 2: Write the probe worker**

`src/index.js`:

```js
/**
 * homgar-telemetry-worker — opt-in anonymous telemetry.
 *
 * TEMPORARY probe build. The only route is /__probe, which exists to answer a
 * single factual question: which request.cf fields does the deployed edge
 * actually populate? This cannot be answered locally — wrangler dev does not
 * populate request.cf at all. Task 7 removes this route.
 */
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/__probe') {
      const cf = request.cf || null;
      return Response.json({
        cf_present: cf !== null,
        keys: cf ? Object.keys(cf).sort() : [],
        values: cf
          ? {
              country: cf.country ?? null,
              city: cf.city ?? null,
              region: cf.region ?? null,
              regionCode: cf.regionCode ?? null,
              postalCode: cf.postalCode ?? null,
              latitude: cf.latitude ?? null,
              longitude: cf.longitude ?? null,
              timezone: cf.timezone ?? null,
              colo: cf.colo ?? null,
              continent: cf.continent ?? null,
              asn: cf.asn ?? null,
              asOrganization: cf.asOrganization ?? null,
            }
          : null,
        cf_ipcountry_header: request.headers.get('CF-IPCountry'),
      });
    }
    return new Response('Not Found', { status: 404 });
  },
};
```

- [ ] **Step 3: Install and deploy**

```bash
cd /Users/brett/Code/homgar-telemetry-worker
npm install
npx wrangler deploy
```

Expected: a `https://homgar-telemetry-worker.<subdomain>.workers.dev` URL is printed. Record it.

- [ ] **Step 4: Call the probe from a real client and record the answer**

```bash
curl -s https://homgar-telemetry-worker.<subdomain>.workers.dev/__probe | python3 -m json.tool
```

Expected: JSON showing `cf_present`, the full `keys` list, and which `values` are non-null.

**This output is the deliverable.** Save it verbatim:

```bash
curl -s https://homgar-telemetry-worker.<subdomain>.workers.dev/__probe \
  > /Users/brett/Code/homgar-telemetry-worker/docs/cf-probe-result.json
```

- [ ] **Step 5: Correct the spec's field table to match observed reality**

Open `docs/superpowers/specs/2026-08-11-optin-telemetry-design.md`, find the
`### What is available to any Cloudflare Worker` section, and:

- Replace the `> **Must be verified...**` warning block with a short note giving
  the date verified and the probe result file path.
- Delete any row from the table whose value came back `null`, and add a sentence
  naming what is genuinely unavailable.
- If only `country`/`colo` are populated, say so plainly — a narrower disclosure
  is a **better** privacy story, and several "never read" rules become "not
  available to read", which is a stronger guarantee than self-restraint. Update
  the prose accordingly rather than leaving it overstated.

- [ ] **Step 6: Commit both repos**

```bash
cd /Users/brett/Code/homgar-telemetry-worker
git add -A
git commit -m "feat: scaffold worker and add temporary edge probe

request.cf is not populated by wrangler dev, so what the deployed edge
actually exposes can only be established by deploying. The /__probe route
records it; Task 7 removes the route."

cd /Users/brett/Code/homeassistant-homgar
git add docs/superpowers/specs/2026-08-11-optin-telemetry-design.md
git commit -m "docs(spec): replace assumed request.cf field table with probe results"
```

---

### Task 2: D1 database and schema

**Files:**
- Create: `/Users/brett/Code/homgar-telemetry-worker/schema.sql`
- Create: `/Users/brett/Code/homgar-telemetry-worker/vitest.config.js`
- Create: `/Users/brett/Code/homgar-telemetry-worker/test/schema.test.js`
- Modify: `/Users/brett/Code/homgar-telemetry-worker/wrangler.toml`

**Interfaces:**
- Consumes: the scaffold from Task 1
- Produces: binding `env.TELEMETRY_DB` (a `D1Database`), and four tables — `installs`, `pings`, `country_counts`, `model_counts`

- [ ] **Step 1: Create the D1 database**

```bash
cd /Users/brett/Code/homgar-telemetry-worker
npx wrangler d1 create homgar-telemetry
```

Copy the printed `database_id` and append to `wrangler.toml`:

```toml
[[d1_databases]]
binding = "TELEMETRY_DB"
database_name = "homgar-telemetry"
database_id = "PASTE_THE_ID_PRINTED_ABOVE"
```

- [ ] **Step 2: Write the schema**

`schema.sql`:

```sql
-- Identifier dimension. Holds NO country and NO device models by design:
-- those are aggregate-only so they cannot be joined back to an install.
CREATE TABLE IF NOT EXISTS installs (
  anon_id            TEXT PRIMARY KEY,
  first_seen         TEXT NOT NULL,   -- "2026-08-11"
  last_seen          TEXT NOT NULL,   -- "2026-08-11"
  last_counted_month TEXT             -- "2026-08", gates monthly aggregation
);

-- Event fact table. DATE only, never a timestamp: this records that an install
-- was active on a given day, not when or for how long. The composite primary
-- key makes writes idempotent and removes all intra-day signal.
CREATE TABLE IF NOT EXISTS pings (
  anon_id             TEXT NOT NULL,
  day                 TEXT NOT NULL,  -- "2026-08-11"
  integration_version TEXT NOT NULL,
  hass_version        TEXT NOT NULL,
  PRIMARY KEY (anon_id, day)
);

CREATE INDEX IF NOT EXISTS idx_pings_day ON pings(day);

-- Aggregate-only. No anon_id column, deliberately.
CREATE TABLE IF NOT EXISTS country_counts (
  country TEXT NOT NULL,
  month   TEXT NOT NULL,
  count   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (country, month)
);

CREATE TABLE IF NOT EXISTS model_counts (
  model TEXT NOT NULL,
  month TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (model, month)
);
```

- [ ] **Step 3: Write the failing schema test**

`vitest.config.js`:

```js
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          d1Databases: ['TELEMETRY_DB'],
        },
      },
    },
  },
});
```

`test/schema.test.js`:

```js
import { env } from 'cloudflare:test';
import { describe, it, expect, beforeAll } from 'vitest';
import { readFileSync } from 'node:fs';

beforeAll(async () => {
  const sql = readFileSync('./schema.sql', 'utf8');
  for (const stmt of sql.split(';').map(s => s.trim()).filter(Boolean)) {
    await env.TELEMETRY_DB.prepare(stmt).run();
  }
});

describe('schema', () => {
  it('creates all four tables', async () => {
    const { results } = await env.TELEMETRY_DB.prepare(
      `SELECT name FROM sqlite_master WHERE type='table' ORDER BY name`
    ).all();
    const names = results.map(r => r.name);
    expect(names).toContain('installs');
    expect(names).toContain('pings');
    expect(names).toContain('country_counts');
    expect(names).toContain('model_counts');
  });

  it('never links country to an install', async () => {
    const { results } = await env.TELEMETRY_DB.prepare(
      `PRAGMA table_info(installs)`
    ).all();
    const cols = results.map(r => r.name);
    expect(cols).not.toContain('country');
    expect(cols).not.toContain('models');
  });

  it('never links an install to the country aggregate', async () => {
    const { results } = await env.TELEMETRY_DB.prepare(
      `PRAGMA table_info(country_counts)`
    ).all();
    expect(results.map(r => r.name)).not.toContain('anon_id');
  });

  it('stores dates, not timestamps, on pings', async () => {
    const { results } = await env.TELEMETRY_DB.prepare(
      `PRAGMA table_info(pings)`
    ).all();
    const cols = results.map(r => r.name);
    expect(cols).toContain('day');
    expect(cols).not.toContain('ts');
    expect(cols).not.toContain('timestamp');
  });
});
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd /Users/brett/Code/homgar-telemetry-worker && npx vitest run test/schema.test.js`
Expected: FAIL — `@cloudflare/vitest-pool-workers` is not installed yet, or the D1 binding is missing.

- [ ] **Step 5: Install test deps and apply the schema remotely**

```bash
npm install
npx wrangler d1 execute homgar-telemetry --remote --file=./schema.sql
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `npx vitest run test/schema.test.js`
Expected: PASS, 4 tests.

- [ ] **Step 7: Commit**

```bash
git add package.json package-lock.json wrangler.toml schema.sql vitest.config.js test/schema.test.js
git commit -m "feat: add D1 schema with aggregate-only country and model tables

Tests assert the structural privacy guarantees directly: installs carries no
country or models column, country_counts carries no anon_id, and pings stores
a date with no timestamp column."
```

---

### Task 3: `POST /ping` — installs upsert and idempotent ping insert

**Files:**
- Modify: `/Users/brett/Code/homgar-telemetry-worker/src/index.js`
- Create: `/Users/brett/Code/homgar-telemetry-worker/test/ping.test.js`

**Interfaces:**
- Consumes: `env.TELEMETRY_DB` from Task 2
- Produces: `handlePing(request, env)` returning `Response`; helpers `isoDay(date) -> "YYYY-MM-DD"` and `isValidAnonId(value) -> boolean`

- [ ] **Step 1: Write the failing test**

`test/ping.test.js`:

```js
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeAll, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';

const ID = '3f2504e0-4f89-41d3-9a0c-0305e82c3301';

beforeAll(async () => {
  const sql = readFileSync('./schema.sql', 'utf8');
  for (const stmt of sql.split(';').map(s => s.trim()).filter(Boolean)) {
    await env.TELEMETRY_DB.prepare(stmt).run();
  }
});

beforeEach(async () => {
  await env.TELEMETRY_DB.batch([
    env.TELEMETRY_DB.prepare('DELETE FROM installs'),
    env.TELEMETRY_DB.prepare('DELETE FROM pings'),
    env.TELEMETRY_DB.prepare('DELETE FROM country_counts'),
    env.TELEMETRY_DB.prepare('DELETE FROM model_counts'),
  ]);
});

function ping(body) {
  return SELF.fetch('https://example.com/ping', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

const BASE = {
  anon_id: ID,
  integration_version: '3.0.44',
  hass_version: '2026.8.1',
  share_country: false,
  share_models: false,
};

describe('POST /ping', () => {
  it('returns 204 with no body', async () => {
    const res = await ping(BASE);
    expect(res.status).toBe(204);
    expect(await res.text()).toBe('');
  });

  it('creates one install row', async () => {
    await ping(BASE);
    const row = await env.TELEMETRY_DB
      .prepare('SELECT * FROM installs WHERE anon_id = ?1').bind(ID).first();
    expect(row.first_seen).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(row.last_seen).toBe(row.first_seen);
  });

  it('is idempotent: twenty pings the same day yield one ping row', async () => {
    for (let i = 0; i < 20; i++) await ping(BASE);
    const row = await env.TELEMETRY_DB
      .prepare('SELECT COUNT(*) AS n FROM pings WHERE anon_id = ?1').bind(ID).first();
    expect(row.n).toBe(1);
  });

  it('records the latest versions on a repeat ping', async () => {
    await ping(BASE);
    await ping({ ...BASE, integration_version: '3.0.45' });
    const row = await env.TELEMETRY_DB
      .prepare('SELECT integration_version FROM pings WHERE anon_id = ?1').bind(ID).first();
    expect(row.integration_version).toBe('3.0.45');
  });

  it('stores a date with no time component', async () => {
    await ping(BASE);
    const row = await env.TELEMETRY_DB
      .prepare('SELECT day FROM pings WHERE anon_id = ?1').bind(ID).first();
    expect(row.day).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('ignores a client-supplied day and uses the worker clock', async () => {
    await ping({ ...BASE, day: '1999-01-01', ts: 915148800 });
    const row = await env.TELEMETRY_DB
      .prepare('SELECT day FROM pings WHERE anon_id = ?1').bind(ID).first();
    expect(row.day).not.toBe('1999-01-01');
    expect(row.day).toBe(new Date().toISOString().slice(0, 10));
  });

  it('rejects a malformed anon_id', async () => {
    const res = await ping({ ...BASE, anon_id: 'not-a-uuid' });
    expect(res.status).toBe(400);
  });

  it('rejects GET', async () => {
    const res = await SELF.fetch('https://example.com/ping', { method: 'GET' });
    expect(res.status).toBe(405);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run test/ping.test.js`
Expected: FAIL — every case 404s, because `/ping` is not routed yet.

- [ ] **Step 3: Implement the handler**

Replace `src/index.js` (keeping the `/__probe` route from Task 1):

```js
/**
 * homgar-telemetry-worker — opt-in anonymous telemetry.
 *
 * PRIVACY RULES (see spec 2026-08-11-optin-telemetry-design.md):
 *   - request.cf.country is the ONLY cf field read anywhere in this file, and
 *     only when the payload sets share_country === true.
 *   - No request body, header, or IP is ever logged. Observability is disabled
 *     in wrangler.toml.
 *   - day/month always come from the worker clock, never from client input.
 */

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isValidAnonId(value) {
  return typeof value === 'string' && UUID_RE.test(value);
}

export function isoDay(date) {
  return date.toISOString().slice(0, 10);
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    switch (url.pathname) {
      case '/ping':
        return handlePing(request, env);
      case '/__probe':
        return handleProbe(request);
      default:
        return new Response('Not Found', { status: 404 });
    }
  },
};

async function handlePing(request, env) {
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return new Response('Bad Request', { status: 400 });
  }

  if (!isValidAnonId(body.anon_id)) {
    return new Response('Bad Request', { status: 400 });
  }

  const anonId = body.anon_id;
  const integrationVersion = String(body.integration_version ?? 'unknown').slice(0, 32);
  const hassVersion = String(body.hass_version ?? 'unknown').slice(0, 32);

  // Worker clock only. A client-supplied day/ts is ignored so a hostile
  // payload cannot forge history.
  const day = isoDay(new Date());

  await env.TELEMETRY_DB.batch([
    env.TELEMETRY_DB.prepare(
      `INSERT INTO installs (anon_id, first_seen, last_seen)
       VALUES (?1, ?2, ?2)
       ON CONFLICT(anon_id) DO UPDATE SET last_seen = ?2`
    ).bind(anonId, day),
    env.TELEMETRY_DB.prepare(
      `INSERT INTO pings (anon_id, day, integration_version, hass_version)
       VALUES (?1, ?2, ?3, ?4)
       ON CONFLICT(anon_id, day) DO UPDATE SET
         integration_version = excluded.integration_version,
         hass_version        = excluded.hass_version`
    ).bind(anonId, day, integrationVersion, hassVersion),
  ]);

  return new Response(null, { status: 204 });
}

function handleProbe(request) {
  const cf = request.cf || null;
  return Response.json({
    cf_present: cf !== null,
    keys: cf ? Object.keys(cf).sort() : [],
    cf_ipcountry_header: request.headers.get('CF-IPCountry'),
  });
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run test/ping.test.js`
Expected: PASS, 8 tests.

- [ ] **Step 5: Commit**

```bash
git add src/index.js test/ping.test.js
git commit -m "feat: POST /ping upserts installs and inserts an idempotent daily ping

The (anon_id, day) primary key makes repeat pings idempotent, so a box that
restarts twenty times is indistinguishable from one that restarts once. The
day comes from the worker clock; a client-supplied day or ts is ignored."
```

---

### Task 4: Monthly aggregates and the privacy regression guard

**Files:**
- Modify: `/Users/brett/Code/homgar-telemetry-worker/src/index.js`
- Create: `/Users/brett/Code/homgar-telemetry-worker/test/aggregates.test.js`
- Create: `/Users/brett/Code/homgar-telemetry-worker/test/privacy.test.js`

**Interfaces:**
- Consumes: `handlePing` from Task 3
- Produces: monthly-gated writes to `country_counts` and `model_counts`

- [ ] **Step 1: Write the failing aggregate test**

`test/aggregates.test.js`:

```js
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeAll, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';

const ID  = '3f2504e0-4f89-41d3-9a0c-0305e82c3301';
const ID2 = '7c9e6679-7425-40de-944b-e07fc1f90ae7';
const MONTH = new Date().toISOString().slice(0, 7);

beforeAll(async () => {
  const sql = readFileSync('./schema.sql', 'utf8');
  for (const stmt of sql.split(';').map(s => s.trim()).filter(Boolean)) {
    await env.TELEMETRY_DB.prepare(stmt).run();
  }
});

beforeEach(async () => {
  await env.TELEMETRY_DB.batch([
    env.TELEMETRY_DB.prepare('DELETE FROM installs'),
    env.TELEMETRY_DB.prepare('DELETE FROM pings'),
    env.TELEMETRY_DB.prepare('DELETE FROM country_counts'),
    env.TELEMETRY_DB.prepare('DELETE FROM model_counts'),
  ]);
});

function ping(body, cf = { country: 'ZA' }) {
  return SELF.fetch('https://example.com/ping', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cf,
  });
}

const BASE = {
  anon_id: ID,
  integration_version: '3.0.44',
  hass_version: '2026.8.1',
  share_country: false,
  share_models: false,
};

async function countryCount(cc) {
  const row = await env.TELEMETRY_DB
    .prepare('SELECT count FROM country_counts WHERE country = ?1 AND month = ?2')
    .bind(cc, MONTH).first();
  return row ? row.count : 0;
}

describe('country aggregation', () => {
  it('does not record country when share_country is false', async () => {
    await ping(BASE);
    expect(await countryCount('ZA')).toBe(0);
  });

  it('records country once when share_country is true', async () => {
    await ping({ ...BASE, share_country: true });
    expect(await countryCount('ZA')).toBe(1);
  });

  it('does not double-count the same install within a month', async () => {
    await ping({ ...BASE, share_country: true });
    await ping({ ...BASE, share_country: true });
    await ping({ ...BASE, share_country: true });
    expect(await countryCount('ZA')).toBe(1);
  });

  it('counts two distinct installs separately', async () => {
    await ping({ ...BASE, share_country: true });
    await ping({ ...BASE, anon_id: ID2, share_country: true });
    expect(await countryCount('ZA')).toBe(2);
  });
});

describe('model aggregation', () => {
  it('ignores models when share_models is false', async () => {
    await ping({ ...BASE, models: ['HTV245FRF'] });
    const row = await env.TELEMETRY_DB
      .prepare('SELECT COUNT(*) AS n FROM model_counts').first();
    expect(row.n).toBe(0);
  });

  it('records each distinct model once when share_models is true', async () => {
    await ping({ ...BASE, share_models: true, models: ['HTV245FRF', 'HTV245FRF', 'HWG023WBRF-V2'] });
    const { results } = await env.TELEMETRY_DB
      .prepare('SELECT model, count FROM model_counts ORDER BY model').all();
    expect(results).toEqual([
      { model: 'HTV245FRF', count: 1 },
      { model: 'HWG023WBRF-V2', count: 1 },
    ]);
  });
});
```

- [ ] **Step 2: Write the failing privacy regression test**

`test/privacy.test.js`:

```js
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeAll, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';

const ID = '3f2504e0-4f89-41d3-9a0c-0305e82c3301';

// Every geolocation field the edge could hand us, all populated with values
// that would be unmistakable if they leaked into storage or a response.
const FULL_CF = {
  country: 'ZA',
  city: 'LEAKED_CITY',
  region: 'LEAKED_REGION',
  regionCode: 'LEAKED_RC',
  postalCode: 'LEAKED_POSTAL',
  latitude: '-33.92500',
  longitude: '18.42410',
  timezone: 'LEAKED_TZ',
  colo: 'LEAKED_COLO',
  continent: 'LEAKED_CONTINENT',
  asn: 99999,
  asOrganization: 'LEAKED_ASORG',
};

beforeAll(async () => {
  const sql = readFileSync('./schema.sql', 'utf8');
  for (const stmt of sql.split(';').map(s => s.trim()).filter(Boolean)) {
    await env.TELEMETRY_DB.prepare(stmt).run();
  }
});

beforeEach(async () => {
  await env.TELEMETRY_DB.batch([
    env.TELEMETRY_DB.prepare('DELETE FROM installs'),
    env.TELEMETRY_DB.prepare('DELETE FROM pings'),
    env.TELEMETRY_DB.prepare('DELETE FROM country_counts'),
    env.TELEMETRY_DB.prepare('DELETE FROM model_counts'),
  ]);
});

async function dumpEverything() {
  const tables = ['installs', 'pings', 'country_counts', 'model_counts'];
  const out = [];
  for (const t of tables) {
    const { results } = await env.TELEMETRY_DB.prepare(`SELECT * FROM ${t}`).all();
    out.push(JSON.stringify(results));
  }
  return out.join('\n');
}

describe('no geo field but country is ever read', () => {
  it('leaks nothing when everything is opted in', async () => {
    const res = await SELF.fetch('https://example.com/ping', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        anon_id: ID,
        integration_version: '3.0.44',
        hass_version: '2026.8.1',
        share_country: true,
        share_models: true,
        models: ['HTV245FRF'],
      }),
      cf: FULL_CF,
    });
    expect(res.status).toBe(204);

    const dump = await dumpEverything();
    for (const marker of [
      'LEAKED_CITY', 'LEAKED_REGION', 'LEAKED_RC', 'LEAKED_POSTAL',
      'LEAKED_TZ', 'LEAKED_COLO', 'LEAKED_CONTINENT', 'LEAKED_ASORG',
      '-33.92500', '18.42410', '99999',
    ]) {
      expect(dump).not.toContain(marker);
    }
    expect(dump).toContain('ZA'); // country IS stored, on opt-in
  });

  it('stores no country at all when location is declined', async () => {
    await SELF.fetch('https://example.com/ping', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        anon_id: ID,
        integration_version: '3.0.44',
        hass_version: '2026.8.1',
        share_country: false,
        share_models: false,
      }),
      cf: FULL_CF,
    });
    const dump = await dumpEverything();
    expect(dump).not.toContain('ZA');
  });
});

describe('source-level guard', () => {
  it('never references a forbidden cf field', () => {
    const src = readFileSync('./src/index.js', 'utf8');
    for (const field of [
      'cf.city', 'cf.region', 'cf.regionCode', 'cf.postalCode',
      'cf.latitude', 'cf.longitude', 'cf.timezone', 'cf.colo',
      'cf.continent', 'cf.asn', 'cf.asOrganization',
      'CF-Connecting-IP',
    ]) {
      expect(src).not.toContain(field);
    }
  });
});
```

> **Note for the implementer:** the source-level guard's status depends on which
> probe version is in the file. Task 1's probe reads every field by name
> (`cf.city`, `cf.latitude`, …) so the guard fails against it; Task 3 replaces it
> with a reduced probe that only calls `Object.keys(cf)`, against which the guard
> passes. Either is fine at this point — the guard's real job is to stay green
> permanently from Task 7 onward, once the probe is gone entirely. If it fails
> here, run `npx vitest run test/privacy.test.js -t 'no geo field'` to exercise
> the behavioural half and move on.

- [ ] **Step 3: Run both tests to verify they fail**

Run: `npx vitest run test/aggregates.test.js`
Expected: FAIL — nothing writes to `country_counts` or `model_counts` yet.

- [ ] **Step 4: Implement aggregation with an atomic monthly claim**

In `src/index.js`, insert this immediately before `return new Response(null, { status: 204 });` in `handlePing`:

```js
  const month = day.slice(0, 7);

  // Atomically claim this month for this install. The UPDATE only matches when
  // the month has not been claimed, so meta.changes === 1 means we won and are
  // the one caller allowed to increment the aggregates. This avoids the
  // read-then-write race a SELECT-based check would have.
  const claim = await env.TELEMETRY_DB.prepare(
    `UPDATE installs SET last_counted_month = ?2
      WHERE anon_id = ?1
        AND (last_counted_month IS NULL OR last_counted_month <> ?2)`
  ).bind(anonId, month).run();

  if (claim.meta.changes === 1) {
    const aggregates = [];

    if (body.share_country === true) {
      // The ONLY read of request.cf in this file.
      const country = request.cf?.country ?? null;
      if (country) {
        aggregates.push(
          env.TELEMETRY_DB.prepare(
            `INSERT INTO country_counts (country, month, count) VALUES (?1, ?2, 1)
             ON CONFLICT(country, month) DO UPDATE SET count = count + 1`
          ).bind(String(country).slice(0, 2), month)
        );
      }
    }

    if (body.share_models === true && Array.isArray(body.models)) {
      const models = [...new Set(body.models.filter(m => typeof m === 'string'))]
        .slice(0, 50)                       // bound a hostile payload
        .map(m => m.slice(0, 64));
      for (const model of models) {
        aggregates.push(
          env.TELEMETRY_DB.prepare(
            `INSERT INTO model_counts (model, month, count) VALUES (?1, ?2, 1)
             ON CONFLICT(model, month) DO UPDATE SET count = count + 1`
          ).bind(model, month)
        );
      }
    }

    if (aggregates.length) await env.TELEMETRY_DB.batch(aggregates);
  }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npx vitest run test/aggregates.test.js && npx vitest run test/privacy.test.js -t 'no geo field'`
Expected: PASS — 6 aggregate tests, 2 privacy behaviour tests.

- [ ] **Step 6: Commit**

```bash
git add src/index.js test/aggregates.test.js test/privacy.test.js
git commit -m "feat: monthly-gated country and model aggregates with a privacy guard

Aggregation is claimed with a conditional UPDATE whose meta.changes decides
the winner, so concurrent pings cannot double-count — a SELECT-then-write
check would race.

The privacy test feeds a cf object with every geolocation field populated
with unmistakable markers and asserts none reaches storage. This is the
regression guard for the README's claim that exactly one field is read."
```

---

### Task 5: `GET /stats` with bearer auth, and `GET /health`

**Files:**
- Modify: `/Users/brett/Code/homgar-telemetry-worker/src/index.js`
- Create: `/Users/brett/Code/homgar-telemetry-worker/test/stats.test.js`

**Interfaces:**
- Consumes: all four tables
- Produces: `GET /stats` (bearer auth) returning `{active_installs, growth, versions, countries, models}`; `GET /health` returning `{status:"ok"}`

- [ ] **Step 1: Write the failing test**

`test/stats.test.js`:

```js
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeAll, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';

const ID = '3f2504e0-4f89-41d3-9a0c-0305e82c3301';
const TOKEN = 'test-stats-token';

beforeAll(async () => {
  const sql = readFileSync('./schema.sql', 'utf8');
  for (const stmt of sql.split(';').map(s => s.trim()).filter(Boolean)) {
    await env.TELEMETRY_DB.prepare(stmt).run();
  }
  env.STATS_TOKEN = TOKEN;
});

beforeEach(async () => {
  await env.TELEMETRY_DB.batch([
    env.TELEMETRY_DB.prepare('DELETE FROM installs'),
    env.TELEMETRY_DB.prepare('DELETE FROM pings'),
    env.TELEMETRY_DB.prepare('DELETE FROM country_counts'),
    env.TELEMETRY_DB.prepare('DELETE FROM model_counts'),
  ]);
});

const stats = (headers = {}) =>
  SELF.fetch('https://example.com/stats', { headers });

describe('GET /stats', () => {
  it('rejects with no token', async () => {
    expect((await stats()).status).toBe(401);
  });

  it('rejects with a wrong token', async () => {
    expect((await stats({ Authorization: 'Bearer nope' })).status).toBe(401);
  });

  it('returns aggregates with a valid token', async () => {
    await SELF.fetch('https://example.com/ping', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        anon_id: ID, integration_version: '3.0.44', hass_version: '2026.8.1',
        share_country: true, share_models: false,
      }),
      cf: { country: 'ZA' },
    });

    const res = await stats({ Authorization: `Bearer ${TOKEN}` });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.active_installs).toBe(1);
    expect(body.countries).toEqual(expect.arrayContaining([
      expect.objectContaining({ country: 'ZA', count: 1 }),
    ]));
  });

  it('never exposes an anon_id', async () => {
    await SELF.fetch('https://example.com/ping', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        anon_id: ID, integration_version: '3.0.44', hass_version: '2026.8.1',
        share_country: false, share_models: false,
      }),
    });
    const res = await stats({ Authorization: `Bearer ${TOKEN}` });
    expect(await res.text()).not.toContain(ID);
  });
});

describe('GET /health', () => {
  it('is public and returns ok', async () => {
    const res = await SELF.fetch('https://example.com/health');
    expect(res.status).toBe(200);
    expect((await res.json()).status).toBe('ok');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run test/stats.test.js`
Expected: FAIL — `/stats` and `/health` 404.

- [ ] **Step 3: Implement**

Add the two cases to the `switch` in `fetch`:

```js
      case '/stats':
        return handleStats(request, env);
      case '/health':
        return Response.json({ status: 'ok' });
```

And append these functions:

```js
/** Constant-time string compare, so token checking does not leak length/prefix. */
function safeEqual(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) {
    return false;
  }
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function handleStats(request, env) {
  const provided = (request.headers.get('Authorization') || '').replace(/^Bearer /, '');
  if (!env.STATS_TOKEN || !safeEqual(provided, env.STATS_TOKEN)) {
    return new Response('Unauthorized', { status: 401 });
  }

  const since = isoDay(new Date(Date.now() - 30 * 86400_000));

  const [active, growth, versions, countries, models] = await env.TELEMETRY_DB.batch([
    env.TELEMETRY_DB.prepare(
      `SELECT COUNT(DISTINCT anon_id) AS n FROM pings WHERE day >= ?1`
    ).bind(since),
    env.TELEMETRY_DB.prepare(
      `SELECT day, COUNT(DISTINCT anon_id) AS installs
         FROM pings WHERE day >= ?1 GROUP BY day ORDER BY day`
    ).bind(since),
    env.TELEMETRY_DB.prepare(
      `SELECT integration_version, hass_version, COUNT(*) AS installs
         FROM pings WHERE day >= ?1
        GROUP BY integration_version, hass_version
        ORDER BY installs DESC`
    ).bind(since),
    env.TELEMETRY_DB.prepare(
      `SELECT country, month, count FROM country_counts ORDER BY month DESC, count DESC`
    ),
    env.TELEMETRY_DB.prepare(
      `SELECT model, month, count FROM model_counts ORDER BY month DESC, count DESC`
    ),
  ]);

  // Note: no query here selects anon_id. Aggregates only.
  return Response.json({
    active_installs: active.results[0]?.n ?? 0,
    growth: growth.results,
    versions: versions.results,
    countries: countries.results,
    models: models.results,
  });
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run test/stats.test.js`
Expected: PASS, 5 tests.

- [ ] **Step 5: Set the production secret**

```bash
npx wrangler secret put STATS_TOKEN
# paste a long random value, e.g. from: openssl rand -hex 32
```

- [ ] **Step 6: Commit**

```bash
git add src/index.js test/stats.test.js
git commit -m "feat: authenticated /stats and public /health

Token comparison is constant-time so it cannot leak length or prefix. A test
asserts no anon_id ever appears in a /stats response — every query in the
handler is an aggregate."
```

---

### Task 6: Retention purge on a cron trigger

**Files:**
- Modify: `/Users/brett/Code/homgar-telemetry-worker/src/index.js`
- Modify: `/Users/brett/Code/homgar-telemetry-worker/wrangler.toml`
- Create: `/Users/brett/Code/homgar-telemetry-worker/test/retention.test.js`

**Interfaces:**
- Consumes: all tables
- Produces: `scheduled(event, env, ctx)` handler; exported `purge(env, now)` for direct testing

- [ ] **Step 1: Write the failing test**

`test/retention.test.js`:

```js
import { env } from 'cloudflare:test';
import { describe, it, expect, beforeAll, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { purge } from '../src/index.js';

const OLD_ID = '3f2504e0-4f89-41d3-9a0c-0305e82c3301';
const NEW_ID = '7c9e6679-7425-40de-944b-e07fc1f90ae7';
const NOW = new Date('2026-08-11T00:00:00Z');

beforeAll(async () => {
  const sql = readFileSync('./schema.sql', 'utf8');
  for (const stmt of sql.split(';').map(s => s.trim()).filter(Boolean)) {
    await env.TELEMETRY_DB.prepare(stmt).run();
  }
});

beforeEach(async () => {
  await env.TELEMETRY_DB.batch([
    env.TELEMETRY_DB.prepare('DELETE FROM installs'),
    env.TELEMETRY_DB.prepare('DELETE FROM pings'),
  ]);
});

describe('retention', () => {
  it('deletes pings older than 395 days and keeps newer ones', async () => {
    await env.TELEMETRY_DB.batch([
      env.TELEMETRY_DB.prepare(
        `INSERT INTO pings VALUES (?1, '2025-01-01', '3.0.44', '2026.1.0')`
      ).bind(OLD_ID),
      env.TELEMETRY_DB.prepare(
        `INSERT INTO pings VALUES (?1, '2026-08-10', '3.0.44', '2026.8.1')`
      ).bind(NEW_ID),
    ]);

    await purge(env, NOW);

    const { results } = await env.TELEMETRY_DB.prepare('SELECT day FROM pings').all();
    expect(results.map(r => r.day)).toEqual(['2026-08-10']);
  });

  it('deletes installs unseen for over 90 days and keeps active ones', async () => {
    await env.TELEMETRY_DB.batch([
      env.TELEMETRY_DB.prepare(
        `INSERT INTO installs (anon_id, first_seen, last_seen) VALUES (?1, '2025-01-01', '2025-01-01')`
      ).bind(OLD_ID),
      env.TELEMETRY_DB.prepare(
        `INSERT INTO installs (anon_id, first_seen, last_seen) VALUES (?1, '2026-08-01', '2026-08-10')`
      ).bind(NEW_ID),
    ]);

    await purge(env, NOW);

    const { results } = await env.TELEMETRY_DB.prepare('SELECT anon_id FROM installs').all();
    expect(results.map(r => r.anon_id)).toEqual([NEW_ID]);
  });

  it('never touches the aggregate tables', async () => {
    await env.TELEMETRY_DB.prepare(
      `INSERT INTO country_counts VALUES ('ZA', '2024-01', 5)`
    ).run();

    await purge(env, NOW);

    const row = await env.TELEMETRY_DB
      .prepare(`SELECT count FROM country_counts WHERE country='ZA' AND month='2024-01'`)
      .first();
    expect(row.count).toBe(5);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run test/retention.test.js`
Expected: FAIL — `purge` is not exported from `src/index.js`.

- [ ] **Step 3: Implement**

Add to `src/index.js`:

```js
const PING_RETENTION_DAYS = 395;    // 13 months, keeps year-on-year comparison
const INSTALL_RETENTION_DAYS = 90;

/**
 * Delete aged rows. Aggregate tables are deliberately never purged — they hold
 * no per-install data, and the historical series is the point.
 */
export async function purge(env, now = new Date()) {
  const pingCutoff    = isoDay(new Date(now.getTime() - PING_RETENTION_DAYS * 86400_000));
  const installCutoff = isoDay(new Date(now.getTime() - INSTALL_RETENTION_DAYS * 86400_000));

  await env.TELEMETRY_DB.batch([
    env.TELEMETRY_DB.prepare(`DELETE FROM pings WHERE day < ?1`).bind(pingCutoff),
    env.TELEMETRY_DB.prepare(`DELETE FROM installs WHERE last_seen < ?1`).bind(installCutoff),
  ]);
}
```

And add a `scheduled` handler to the default export, after `fetch`:

```js
  async scheduled(event, env, ctx) {
    ctx.waitUntil(purge(env));
  },
```

Add to `wrangler.toml`:

```toml
[triggers]
crons = ["17 3 * * *"]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run test/retention.test.js`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/index.js wrangler.toml test/retention.test.js
git commit -m "feat: daily retention purge for pings and stale installs

Pings age out at 395 days (13 months, preserving year-on-year comparison);
installs unseen for 90 days are removed so active counts stay honest. The
aggregate tables are never purged — they hold no per-install data and the
historical series is the whole point."
```

---

### Task 7: Remove the probe, harden, and write the README disclosure

This task makes the source-level privacy guard from Task 4 pass, and produces the public-facing document the whole design rests on.

**Files:**
- Modify: `/Users/brett/Code/homgar-telemetry-worker/src/index.js` (delete probe)
- Create: `/Users/brett/Code/homgar-telemetry-worker/README.md`

**Interfaces:**
- Consumes: everything
- Produces: a deployed worker with exactly three routes and a published README

- [ ] **Step 1: Delete the probe route**

Remove the `case '/__probe':` line from the `switch`, and delete the entire
`handleProbe` function. It is the only code in the file that reads forbidden
`cf` fields, and it has served its purpose.

- [ ] **Step 2: Run the full suite, including the source guard**

Run: `npx vitest run`
Expected: PASS, all suites — including `source-level guard › never references a
forbidden cf field`, which was expected to fail while the probe existed.

- [ ] **Step 3: Write the README**

`README.md`. Use the **probe results from Task 1** for the field table — not the
spec's original assumed list. If the probe showed only `country` and `colo` are
populated, say exactly that; a narrower disclosure is a better privacy story, and
several "we never read" rules become "not available to read", which is stronger.

Required sections:

1. **What this is** — one paragraph; opt-in, off by default, anonymous.
2. **Exactly what is stored** — paste `schema.sql` verbatim.
3. **What Cloudflare sees before our code runs** — the verified field table, and
   this text:
   > Cloudflare terminates the connection and therefore sees your IP address, as
   > any web server does — we never read, log, or store it. Cloudflare also
   > derives geolocation at the edge automatically, before our code runs. We do
   > not request this and cannot switch it off.
4. **Verify it yourself, on someone else's site** — link
   `https://www.cloudflare.com/cdn-cgi/trace`, note it is Cloudflare's own
   domain and unaffiliated with this project, show a sample response, and note
   the same endpoint exists on nearly every Cloudflare-fronted site so the reader
   can confirm on unrelated domains that this is ordinary web infrastructure.
5. **Retention** — 395 days for activity dates, 90 days for inactive installs,
   aggregates kept indefinitely. State plainly that the dates an install was
   active are retained, dates only and never times.
6. **How to opt out** — turn the switch off in Home Assistant; no further pings.

- [ ] **Step 4: Deploy and smoke-test**

```bash
npx wrangler deploy
curl -s -o /dev/null -w '%{http_code}\n' https://<worker-url>/health          # 200
curl -s -o /dev/null -w '%{http_code}\n' https://<worker-url>/__probe         # 404
curl -s -o /dev/null -w '%{http_code}\n' https://<worker-url>/stats           # 401
curl -s -X POST https://<worker-url>/ping -H 'Content-Type: application/json' \
  -d '{"anon_id":"3f2504e0-4f89-41d3-9a0c-0305e82c3301","integration_version":"3.0.44","hass_version":"2026.8.1","share_country":false,"share_models":false}' \
  -o /dev/null -w '%{http_code}\n'                                            # 204
```

- [ ] **Step 5: Confirm nothing is being logged**

```bash
npx wrangler tail --format pretty
# In another shell, send a ping. The tail must show no request body and no IP.
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: remove probe, add README disclosure, deploy

Deleting the probe makes the source-level privacy guard pass: no forbidden cf
field is referenced anywhere in the worker.

The README documents the verified field list rather than the assumed one, and
points at Cloudflare's own /cdn-cgi/trace so readers can confirm the edge
geolocation behaviour without trusting us."
```

---

## Done when

- `npx vitest run` is green across all six suites (`schema`, `ping`,
  `aggregates`, `privacy`, `stats`, `retention`).
- The deployed worker answers `/health` 200, `/ping` 204, `/stats` 401 without a
  token and 200 with one, and `/__probe` 404.
- `wrangler tail` shows no request body, header, or IP during a ping.
- The README's field table matches the recorded probe output.
- The spec's field table has been corrected to match reality.

**Next:** the integration-side plan (`v3.0.44`) is written *after* this, because
the opt-in notification and README wording depend on the verified answer to what
Cloudflare actually exposes.
