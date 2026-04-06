# HomGar/RainPoint Integration - Project Reference

## Project Overview

Home Assistant custom integration for HomGar and RainPoint cloud-connected irrigation devices.

**Main Repository:** `/Users/brettmeyerowitz/Code/homeassistant-homgar`
**GitHub:** https://github.com/brettmeyerowitz/homeassistant-homgar

## Related Repositories

### Cloudflare Debug Worker
**Location:** `/Users/brettmeyerowitz/homeassistant-homgar-debug-worker`
**Purpose:** Collects anonymous debug data to improve decoder accuracy
**URL:** https://homgar-debug-worker.funkypeople.workers.dev
**Documentation:** `docs/cloudflare_worker.md`

### Reference Implementation
**GitHub:** https://github.com/martinpeniak/tao-irrigation
**Purpose:** Working MQTT implementation for Alibaba Cloud IoT Platform
**Used for:** MQTT authentication and message parsing patterns

## Key Integration Components

### Core Files
- `custom_components/homgar/__init__.py` - Integration setup, MQTT initialization
- `custom_components/homgar/manifest.json` - Integration metadata, version, dependencies
- `custom_components/homgar/const.py` - Constants, version, configuration keys
- `custom_components/homgar/config_flow.py` - Configuration UI
- `custom_components/homgar/coordinator.py` - Data update coordinator

### API & Decoders
- `custom_components/homgar/api/client.py` - HomGar/RainPoint API client, MQTT credentials
- `custom_components/homgar/api/decoders.py` - Device payload decoders (all models)
- `custom_components/homgar/mqtt_client.py` - MQTT client for real-time updates
- `custom_components/homgar/coordinator_mqtt.py` - MQTT message handler for coordinator

### Platform Entities
- `custom_components/homgar/sensor.py` - Sensor entities (moisture, temp, humidity, etc.)
- `custom_components/homgar/valve.py` - Valve entities (irrigation control)
- `custom_components/homgar/number.py` - Number entities (duration, settings)
- `custom_components/homgar/switch.py` - Switch entities (debug switch)

### Debug & Utilities
- `custom_components/homgar/debug.py` - Debug data submission to Cloudflare Worker
- `custom_components/homgar/country_codes.py` - Region/country code mappings

## Docker Testing Environment

**Container Name:** `ha-test`

### Common Commands
```bash
# Copy integration to Docker
docker cp custom_components/homgar ha-test:/config/custom_components/

# Restart container
docker restart ha-test

# Check logs
docker logs ha-test 2>&1 | grep -E "(HomGar|MQTT|error)"

# Check version loaded
docker logs ha-test 2>&1 | grep "HomGar v"

# Follow logs
docker logs -f ha-test
```

## Version Management

### Version Files (Always Update Together)
1. `custom_components/homgar/manifest.json` - `"version": "X.Y.Z"`
2. `custom_components/homgar/const.py` - `VERSION = "X.Y.Z"`
3. `README.md` - Example manifest section
4. `CHANGELOG.md` - Add new version entry

### Versioning Strategy
- **Major (X.0.0):** Breaking changes, new dependencies, architecture changes
- **Minor (x.Y.0):** New features, new device support, non-breaking changes
- **Patch (x.y.Z):** Bug fixes, decoder improvements, documentation updates

## Supported Devices

### Hubs
- **HWG023WRF** / **HWG023WBRF-V2** - Main hub (RF + WiFi)
- **HWS019WRF-V2** - Display hub (temperature, humidity, pressure)

### Valves
- **HTV0540FRF** - 4-zone valve controller (TLV format)
- **HTV213FRF** - 2-zone valve controller (hex/ASCII format)
- **HTV245FRF** - 4-zone valve controller (hex/ASCII format)

### Sensors
- **HCS021FRF** - Soil moisture + temperature + illuminance
- **HCS026FRF** - Soil moisture (simple)
- **HCS014ARF** - Outdoor temperature + humidity
- **HCS012ARF** - Rain sensor
- **HCS008FRF** - Flow meter
- **HCS0528ARF** - Pool temperature sensor
- **HCS0530THO** - CO2 + temperature + humidity

### Unsupported (Reported)
- **HIC801W** - Unknown device type (Issue #20)

## Decoder Architecture

### Payload Formats
1. **Hex Format:** `10#` or `11#` prefix, hex-encoded bytes
2. **ASCII Format:** Comma/semicolon separated values (valves)
3. **TLV Format:** Type-Length-Value structure (some valves)

### Decoder Patterns
- **RainPoint Exact Parsing:** Bit manipulation for DP entries
- **Valve State:** Bit 0 logic (`bool(state & 0x01)`)
- **Temperature:** Various formats (F10, C, raw values)
- **RSSI:** Byte 1, negate for dBm

### Key Decoder Functions
- `_parse_homgar_payload()` - Strip prefix, convert hex to bytes
- `_parse_tlv_payload()` - Parse TLV structure
- `_extract_rssi()` - Extract RSSI from byte 1
- `_le16()` - Little-endian 16-bit integer
- `_battery_status_to_percent()` - Convert status code to percentage

## MQTT Implementation

### Alibaba Cloud IoT Platform
- **Authentication:** HMAC-SHA1, securemode=3
- **Client ID:** `{deviceName}|securemode=3,signmethod=hmacsha1|`
- **Username:** `{deviceName}&{productKey}`
- **Password:** HMAC-SHA1 signature (no timestamp)
- **Topic:** `/sys/{productKey}/{deviceName}/thing/service/property/set`

### Message Format
```
{"params": {"param": "#P{timestamp}{uid}|{hub_mid}|{D01: {...}}|..."}}
```

### MQTT Credentials
Extracted from login API response:
- `productKey` - From user.productKey
- `deviceName` - From user.deviceName
- `deviceSecret` - From user.deviceSecret
- `mqttHostUrl` - From mqttHostUrl field

## Known Issues & Fixes

### Issue #11 - HTV213FRF Valve State
**Problem:** Valves always showing "on"
**Cause:** Incorrect state detection logic
**Fix:** Use bit 0 logic: `bool(state & 0x01)` instead of `state != 0x00`
**Affected:** Both hex and ASCII decoders
**Fixed in:** v2.0.0 (TLV), v2.0.1 (hex custom decoder)

### Issue #21 - HCS014ARF Decoder
**Problem:** Temperature and humidity not extracted
**Cause:** Basic decoder stub, no field extraction
**Fix:** Implemented full decoder with user-provided formula
**Fields:** Bytes 10-11 (temp in F10), Byte 13 (humidity)
**Fixed in:** v2.0.1

### Cloudflare Worker Empty Data
**Problem:** Decoded values showing as `{}`
**Cause:** Field mapping mismatch in debug.py
**Fix:** Updated field_mappings to handle new decoder field names
**Fixed in:** v2.0.1

## Git Workflow (CRITICAL)

### Release Process
1. Update code implementation
2. **Test in Docker first** (always!)
3. Bump version in manifest.json AND const.py
4. Update CHANGELOG.md
5. Update README.md version
6. Create `commit_message.txt`
7. Create `release_notes_vX.X.X.md`
8. Commit: `git commit -F commit_message.txt`
9. Push: `git push origin main`
10. Tag: `git tag vX.X.X && git push origin vX.X.X`
11. Release: `gh release create vX.X.X --notes-file release_notes_vX.X.X.md`
12. Cleanup: `rm commit_message.txt release_notes_vX.X.X.md`

### File-Based Operations (MANDATORY)
- ✅ **ALWAYS** use text files for commit messages
- ✅ **ALWAYS** use text files for release notes
- ✅ **ALWAYS** use text files for issue comments
- ❌ **NEVER** write large text blocks directly in terminal

## Testing Requirements

### Pre-Release Checklist
- [ ] Docker testing completed
- [ ] No import errors in logs
- [ ] Version number appears in logs
- [ ] All decoders load correctly
- [ ] Real device data processes successfully
- [ ] Version bumped in all files
- [ ] CHANGELOG.md updated
- [ ] README.md updated

### Docker Test Commands
```bash
# Full test cycle
docker cp custom_components/homgar ha-test:/config/custom_components/
docker restart ha-test
sleep 15
docker logs ha-test 2>&1 | grep "HomGar v"
docker logs ha-test 2>&1 | grep -i error | tail -20
```

## Documentation Files

### User Documentation
- `README.md` - Main integration documentation
- `CHANGELOG.md` - Version history and changes

### Developer Documentation
- `docs/cloudflare_worker.md` - Cloudflare Worker details
- `docs/project_reference.md` - This file
- `docs/dean_valve_issue_analysis.md` - Issue #11 analysis
- `DEVELOPMENT.md` - Development setup (if exists)

### Test Data
- `mqtt_test_credentials.py` - MQTT credential generator
- `docs/deanlog.txt` - Real device logs for testing

## External Resources

### APIs
- **HomGar API:** region{X}.homgarus.com (X = 1-5)
- **RainPoint API:** region{X}.rainpointus.com (X = 1-5)
- **Endpoints:** /login, /device/list, /device/status, /device/multipleDeviceStatus

### Dependencies
- `paho-mqtt>=1.6.0` - MQTT client library
- Home Assistant core libraries (aiohttp, etc.)

## Current Status (v2.0.1)

### Completed
- ✅ MQTT real-time updates
- ✅ Valve state fix (bit 0 logic)
- ✅ HCS014ARF decoder implementation
- ✅ Cloudflare Worker field mappings
- ✅ Version bumped to 2.0.1

### Pending
- [ ] CHANGELOG.md update
- [ ] README.md update
- [ ] Docker testing
- [ ] User approval for release
- [ ] GitHub commit and release

### Open Issues
- **#19** - HCS021FRF data freezing (Dean)
- **#20** - HIC801W unsupported sensor
- **#17** - Valve control "illegal param" error (Dean)

## Contact & Support

### GitHub Issues
https://github.com/brettmeyerowitz/homeassistant-homgar/issues

### Key Contributors
- @brettmeyerowitz - Maintainer
- Community contributors via issues and PRs

## Notes

- **No Android app references** in documentation (user requirement)
- **Always test in Docker** before release
- **File-based git operations** mandatory
- **User approval required** before GitHub commits
