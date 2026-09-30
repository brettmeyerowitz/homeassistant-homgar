# Model catalogue — design

Status: proposed, not built.
Date: 2026-09-30

## Problem

Two gaps, both of which cost us this month.

**1. We publish SKUs and nothing else.** The README lists 109 model numbers and
no product names. Someone who has just bought a flow meter searches for what is
printed on the box; `HCS048B` tells them nothing about what it is, and tells us
nothing when they ask for help. The Discord report that started this was
literally *"I bought a RainPoint HCS048B Wireless Water Flow Meter"* — the user
did that mapping himself because we do not publish it.

**2. What we know about specific models is scattered.** Seven facts across five
files, with one written out three times:

| What we know | Where it lives now |
|---|---|
| Needs the DP control endpoint despite exposing `CTL_WATER` | `decoder.py:153` |
| `STA_RH` means soil moisture, not air humidity (12 models) | `decoder.py:234` |
| Reports rain state | `decoder.py:249` |
| Bluetooth-only, unreadable over the cloud | `generate-supported-devices.py:44` |
| Sensor label overrides | `sensor.py:63` |
| `HWS019WRF-V2` takes battery/signal from the hub | `decoder.py:590`, `coordinator.py:449`, `coordinator_mqtt.py:132` |
| `HIC801W` encodes the active zone as an ordinal, not a bitmask | `decoder.py:1245` |

Nobody can answer "what do we know about model X" without grepping. That is how
the `HCS048B` went five months and two bug reports before anyone established it
was Bluetooth-only and could never have worked.

## What this is

One file, `custom_components/homgar/data/model_catalogue.json`, shipped next to
`product_models.json`, holding **only what the vendor catalogue does not tell
us**. Keyed by model:

```json
{
  "HCS048B": {
    "name": "Wireless Water Flow Meter",
    "manual": "https://service.rainpointonline.com/hc/en-us/articles/...",
    "transport": "bluetooth_only"
  },
  "HCS044FRF": {
    "name": "...",
    "humidity_is_soil_moisture": true,
    "reports_rain_state": true,
    "sensor_labels": { "event_time": "Rain Event Time" }
  },
  "HIC801W": { "name": "...", "zone_encoding": "ordinal" }
}
```

Descriptive fields for models people own; behavioural traits only for the
exceptions. Most models get a name and nothing else, which is the point — the
behavioural half stays a short list of exceptions rather than a mirror of the
catalogue.

### Attributes

**Descriptive**
* `name` — the product name from the manual cover
* `manual` — link to the vendor manual

**Behavioural** (the seven that exist today, lifted as-is)
* `humidity_is_soil_moisture`, `reports_rain_state`,
  `control_endpoint: "dp"`, `transport: "bluetooth_only"`,
  `battery_and_signal_from_hub`, `zone_encoding: "ordinal"`, `sensor_labels`

**New, because we learned them and wrote them nowhere**
* `duration_unit: "minutes"` — the seven HIC controllers. Derived structurally
  today by `uses_minute_duration()`, which is elegant but silently opinionated
  about six models nobody has tested. Recording it makes the claim greppable.
* `legacy_dialect` — `valve` / `meter` / `weather` / `multizone`. The decoder
  infers this at runtime from field counts; the heuristic works but is
  invisible, and an invisible field map is what was wrong for a year.
* `verified` — `hardware` / `corpus` / `inferred`, only where a trait is not
  directly observed. Writing honest PR bodies this month meant reconstructing
  "how do we actually know this?" from memory twice.

## Scope: the models people own

Names come from the manual PDFs, so this is manual work. It is not worth doing
for all 109 advertised models at once.

Telemetry shows **39 distinct models actually owned**, which is the starting
set — a third of the list, ordered by how many people have one. The top ten
alone (`HWG023WBRF-V2`, `HCS012ARF`, `HCS026FRF`, `HCS021FRF`, `HTV145FRF`,
`HWG0538WRF`, `HTV245FRF`, `HWG023WRF`, `HTV213FRF`, `HTV405FRF`) cover most
installs. The rest can fill in as people turn up with them.

Telemetry only counts people who opted into model sharing, so 39 is a lower
bound, not a census.

## What stays derived from the vendor catalogue

`get_valve_ports`, `get_switch_ports`, `uses_minute_duration`,
`uses_ble_valve_control`. These already extend to new models automatically,
which is the property we want. Anything derivable — port counts, dp identities,
valve capability — stays derived. Copying it in creates a second source of
truth that drifts.

## Deferred: the alias map

What is printed on the box is often not what the cloud reports. Of 66 SKUs in
the vendor's own manual index, **only 11 are in our catalogue**. The rest are
retail SKUs (`HGS-Z238`, `IK159`, `ITV256`), kit bundles
(`HTV245FRF+HWG023WBRF`), what look like rebrands (the `TTV*`/`TWG*` line
mirrors `HTV*`/`HWG*` almost exactly), and near-misses — the index lists
`HWG009BW` where our catalogue has `HWG009WB`, transposed.

An `aliases` field mapping box SKU to cloud model is the higher-value half,
because it closes the gap people actually fall into. It also needs the most
sourcing, so it comes second.

## Validation

A test that fails loudly rather than silently doing nothing:

* every model named in the file exists in the vendor catalogue — catches typos
  and models the vendor has dropped
* every attribute name is one the code or the README generator consumes —
  catches an attribute written but never wired up, or renamed in code but not
  in data
* no model carries an empty object

## What this does not solve

**A genuinely new model still needs a release**, because the catalogue ships
with the integration. That was a deliberate 3.1.0 decision — decoding stays
offline so nobody's Home Assistant depends on the vendor being reachable — and
this does not revisit it. What it improves is knowing, when a new model
arrives, whether it needs anything beyond its catalogue row. The refresh
available today adds `HTV368FRF`, `HTV468FRF` and `HWS578WRF-V8`, and the only
way to judge whether any needed attention was to reason from the naming
convention.

## Build order

1. The file, loader and validation test, carrying today's seven behavioural
   facts and names for the top ten owned models. Nothing reads it yet.
2. README generator reads `name`, so the supported list becomes readable.
   This is the change users see.
3. Switch behavioural consumers over one at a time, deleting each constant as
   its consumer moves. Behaviour-preserving; the existing suites are the check.
4. `HWS019WRF-V2` last, since it is the only one touching the MQTT path as well
   as the decoder.
5. Names for the remaining owned models, as people turn up with them.
6. Alias map, separately.

## Open question

Should a trait be able to override a derived predicate — forcing minute
duration on a model the structural rule misses? Additive and orthogonal to
start with. Allowing overrides turns the file into a configuration language and
invites exactly the drift this is meant to end.
