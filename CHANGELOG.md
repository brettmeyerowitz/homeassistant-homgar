# Changelog

All notable changes to this project will be documented in this file.

## [1.3.0] - 2026-03-28

### Added
- **30+ new device decoder implementations** - Comprehensive support for all HCS sensor series
  - HCS005FRF, HCS003FRF - Moisture-only sensors
  - HCS024FRF-V1 - Multi-sensor (temp+moisture+lux)
  - HCS014ARF, HCS027ARF, HCS016ARF - Temperature/humidity sensors
  - HCS015ARF, HCS0528ARF - Pool temperature sensors
  - HCS044FRF, HCS666FRF, HCS666RFR-P, HCS999FRF, HCS999FRF-P, HCS666FRF-X - Advanced sensor variants
  - HCS701B, HCS596WB, HCS596WB-V4 - Wall-mounted and weather station sensors
  - HCS706ARF, HCS802ARF, HCS048B, HCS888ARF-V1, HCS0600ARF - Environmental sensors
- **97+ new sensor entities** automatically created across all device types
- **Helper methods** for standardized payload parsing:
  - `_extract_rssi()` - RSSI extraction
  - `_extract_status_code()` - Battery status parsing
  - `_validate_payload()` - Payload validation
  - `_validate_tag()` - Sensor tag verification
  - `_base_decoder_dict()` - Consistent return structure

### Improved
- **Refactored all existing decoders** to use helper methods - eliminated 200+ lines of duplicate code
- **Better error handling** - Standardized validation and error messages across all decoders
- **Improved reliability** for HCS021FRF (Issue #12) - Better payload validation and error handling
- **Enhanced logging** - More detailed debug information for troubleshooting
- **Code maintainability** - Consistent patterns make adding new devices easier

### Fixed
- **HCS021FRF unavailable issues** (Issue #12) - Improved decoder validation and error handling
  - Decoder implementation verified against official protocol specification
  - Added `_validate_tag()` to ensure payload format matches expected structure
  - Better error messages when payload doesn't match expected format
  - Enhanced logging shows exact byte positions where validation fails
  - **For users still seeing "unavailable"**: Enable debug logging to see if device is reporting data or if it's an API/connectivity issue
- **Display hub garbled values** (Issue #8) - Better error handling and logging for debugging
- Missing MODEL_HCS0528ARF constant added to const.py

### Technical
- All decoders now use standardized helper methods
- Proper device class and icon configuration for all sensor types
- Complete Home Assistant entity integration for all new devices
- Coordinator properly maps all 21 new device models to decoders
- Sensor platform creates appropriate entities for each device type

## [1.2.0] - 2026-03-28

### Added
- **Full valve hub support (HTV0540FRF)** - Thanks to @gavinwoolley!
  - Valve entities for open/close control per zone
  - Duration number entities (1-60 min) per zone
  - Dynamic zone detection from payload
  - Immediate state reflection after commands
- **Valve platform** - New valve entities for irrigation control
- **Number platform** - Duration configuration entities

### Improved
- TLV payload parsing for valve devices
- Coordinator now supports valve hub decoding
- Added valve models to recognized devices list

### Technical
- Added `decode_valve_hub()` function with TLV parsing
- Added `valve.py` and `number.py` platforms
- Updated coordinator to handle valve sub-devices

## [1.1.0] - 2026-03-28

### Added
- **Icons for all sensor types** - Better visual identification in UI
  - Moisture sensors: `mdi:water-percent`
  - Temperature sensors: Use default temperature icon
  - Illuminance sensors: `mdi:brightness-5`
  - Rain sensors: `mdi:weather-rainy`
  - Raw payload sensors: `mdi:code-braces`
- **Recognized valve models** - HTV213FRF, HTV245FRF, HTV0540FRF now recognized (support pending payload data)
- **Debug documentation** - Added DEBUG_VALVE_PAYLOAD.md for users to help capture valve payload data

### Improved
- **Entity organization** - Raw payload sensors marked as diagnostic entities (disabled by default)
- **Better error messages** - Improved logging for unsupported devices with GitHub issue reporting instructions
- **Code documentation** - Added comments for valve model recognition

### Fixed
- All devices now correctly branded as "RainPoint" hardware regardless of app type selection

## [1.0.0] - 2026-03-28

### Added
- Initial official release
- Full HomGar and RainPoint app type support
- Proper translation support via translations/en.json
- Support for multiple sensor types:
  - HCS021FRF (Moisture + Temperature + Light)
  - HCS026FRF (Moisture sensor)
  - HCS012ARF (Rain sensor)
  - HCS014ARF (Temperature/Humidity)
  - HCS008FRF (Flowmeter)
  - HCS0530THO (CO2/Temp/Humidity)
  - HCS0528ARF (Pool/Temperature)
  - HCS015ARF+ (Pool + Ambient)
  - HWS019WRF-V2 (Display Hub)

### Fixed
- **Critical**: Fixed login to use dynamic appCode based on user selection
- **Critical**: Fixed sensor creation bug (was checking wrong key in multipleDeviceStatus response)
- Removed incorrect strings.json translation file

### Improved
- Efficient multipleDeviceStatus API with automatic fallback to individual calls
- Comprehensive error handling
- Proper device classes for all sensor types
- App-agnostic error messages
