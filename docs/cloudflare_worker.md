# Cloudflare Worker - Debug Data Collection

## Overview

The HomGar integration includes a Cloudflare Worker for collecting anonymous debug data from users to help improve decoder accuracy and discover new device patterns.

## Repository Location

**Worker Repository:** `/Users/brettmeyerowitz/homeassistant-homgar-debug-worker`

**Deployed URL:** https://homgar-debug-worker.funkypeople.workers.dev

## Endpoints

### `/submit` (POST)
Receives debug data submissions from Home Assistant integrations.

**Expected Data Format:**
```json
{
  "device_model": "HCS014ARF",
  "device_type": "temphum",
  "raw_payload": "10#E74A022603DC01B8058560028843E92561FF0F0F7C0B19",
  "decoded_values": {
    "temperature": 16.0,
    "humidity": 67,
    "co2": 456,
    "moisture": 35,
    "illuminance": 577.4,
    "flow": 123.4,
    "pressure": 1013.2,
    "rain": 16.0
  },
  "metadata": {
    "rssi": -74,
    "battery": 100,
    "firmware": "53",
    "device_timestamp": "2026-04-06T07:30:00.000Z",
    "device_name": "Sensor Name",
    "hub_name": "Hub Name"
  },
  "integration_version": "2.0.1"
}
```

### `/view` (GET)
Web interface for viewing collected debug data.

**Query Parameters:**
- `device` - Filter by device model (optional)
- `limit` - Number of submissions to show (default: 50)

**Example:** https://homgar-debug-worker.funkypeople.workers.dev/view?device=HCS014ARF&limit=25

### `/json` (GET)
JSON API endpoint for programmatic access to submissions.

**Query Parameters:**
- `device` - Filter by device model (optional)
- `limit` - Number of submissions to show (default: 50)

**Response Format:**
```json
{
  "total": 10,
  "device_filter": "HCS014ARF",
  "submissions": [
    {
      "id": "uuid",
      "timestamp": "2026-04-06T07:00:00.000Z",
      "device_model": "HCS014ARF",
      "device_type": "temphum",
      "raw_payload": "10#E74A022603DC01B807855A028842E92561FF0FB36A0B19",
      "decoded_values": {
        "temperature": 15.7,
        "humidity": 66
      },
      "metadata": {
        "rssi": -74,
        "battery": 100,
        "firmware": "12"
      }
    }
  ]
}
```

**Example:** https://homgar-debug-worker.funkypeople.workers.dev/json?device=HCS014ARF&limit=25

**Use Cases:**
- Automated testing of decoders
- Batch analysis of payloads
- Integration with external tools
- Quick data extraction without HTML parsing

### `/health` (GET)
Health check endpoint.

### `/stats` (GET)
Statistics about collected data.

## Integration Code

### Data Submission

**File:** `custom_components/homgar/debug.py`

The integration submits data via the `HomGarDebugSwitch` entity when enabled by the user.

**Key Configuration:**
- `DEBUG_WORKER_URL` in `const.py`: https://homgar-debug-worker.funkypeople.workers.dev/submit
- `DEBUG_SUBMISSION_INTERVAL`: 24 hours (86400 seconds)

### Field Mappings

The integration maps decoder field names to worker field names in `debug.py`:

```python
field_mappings = {
    "co2": ["co2_ppm", "co2"],
    "temperature": ["temperature_c", "temperature"],
    "humidity": ["humidity_percent", "humidity"],
    "moisture": ["moisture_percent", "moisture"],
    "illuminance": ["illuminance_lux", "illuminance"],
    "flow": ["flowcurrentused", "flow"],
    "pressure": ["pressure_mb", "pressure"],
    "rain": ["rain_last_24h_mm", "rain_total_mm", "rain"],
}
```

**Important:** When adding new decoder fields, update these mappings to ensure data is submitted correctly to the worker.

## Worker Implementation

### Technology Stack
- **Platform:** Cloudflare Workers
- **Storage:** Cloudflare KV (Key-Value store)
- **Language:** JavaScript (ES modules)
- **Dependencies:** uuid (for submission IDs)

### Key Files
- `src/index.js` - Main worker code
- `wrangler.toml` - Cloudflare configuration
- `package.json` - Node.js dependencies

### Data Storage
- **Key Format:** `submission:{uuid}`
- **Retention:** Configured via `DATA_RETENTION_DAYS` environment variable
- **Storage:** Cloudflare KV namespace `DEBUG_DATA`

### Viewer Interface
The `/view` endpoint generates an HTML interface showing:
- Raw payloads
- Decoded values (JSON formatted)
- Metadata (RSSI, battery, firmware, timestamps)
- Device model badges
- Copy-to-clipboard functionality
- Device filtering
- Statistics (total submissions, device models)

## Deployment

### Deploy Worker
```bash
cd /Users/brettmeyerowitz/homeassistant-homgar-debug-worker
npm install
npx wrangler deploy
```

### Configuration
Edit `wrangler.toml` for:
- Worker name
- KV namespace bindings
- Environment variables
- Routes

## Troubleshooting

### Empty Decoded Values
**Symptom:** Worker shows `{}` for decoded_values

**Cause:** Field mapping mismatch between decoder output and debug.py mappings

**Fix:** Update `field_mappings` in `debug.py` to include new decoder field names

**Example Issue (v2.0.1):**
- HCS014ARF decoder returns `temperature_c`, `humidity_percent`
- Old mappings only checked for `temperature`, `humidity`
- Solution: Added fallback field names in mappings

### No Data Submissions
**Check:**
1. Debug switch enabled in Home Assistant
2. Integration version includes debug.py
3. Network connectivity to Cloudflare
4. Worker logs in Cloudflare dashboard
5. KV namespace properly bound

## Privacy & Data Collection

### Anonymous Data
All submitted data is anonymous:
- No user identifiers
- No location data
- No IP addresses stored
- Only device models, payloads, and decoded values

### Purpose
- Improve decoder accuracy
- Discover new device patterns
- Validate decoder implementations
- Help users with unsupported devices

### User Control
- Opt-in only (disabled by default)
- Can be disabled anytime via debug switch
- Data expires after retention period
- No personal information collected

## Version History

### v2.0.1 (2026-04-06)
- Fixed field mappings for new decoder field names
- Added support for `temperature_c`, `humidity_percent`, etc.
- Updated to handle multiple possible field names per value

### v2.0.0 (2026-04-02)
- Initial debug worker implementation
- Basic submission and viewing functionality
- KV storage integration

## Related Files

### Integration Files
- `custom_components/homgar/debug.py` - Debug switch and submission logic
- `custom_components/homgar/const.py` - Worker URL and configuration
- `custom_components/homgar/switch.py` - Switch platform setup

### Worker Files
- `/Users/brettmeyerowitz/homeassistant-homgar-debug-worker/src/index.js`
- `/Users/brettmeyerowitz/homeassistant-homgar-debug-worker/wrangler.toml`
- `/Users/brettmeyerowitz/homeassistant-homgar-debug-worker/package.json`

## Future Enhancements

### Planned Features
- Pattern analysis and anomaly detection
- Automatic decoder suggestions
- Device comparison tools
- Export functionality
- API for programmatic access
- Statistics dashboard
- Device model documentation generator

### Integration Improvements
- Automatic submission on new device detection
- Payload validation before submission
- Retry logic for failed submissions
- Submission history in UI
- Manual submission trigger
