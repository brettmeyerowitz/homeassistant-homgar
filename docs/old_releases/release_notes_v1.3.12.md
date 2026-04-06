# HomGar/RainPoint Cloud Integration v1.3.12

## 🎉 Major New Feature: Community Debug Data Collection

This release introduces a groundbreaking debug data collection system that enables community-driven improvement of device decoder accuracy while maintaining strict privacy protections.

## ✨ What's New

### 🔍 Debug Data Submission System
- **"Submit Debug Data" Switch**: New entity in Home Assistant for voluntary data sharing
- **Anonymous Collection**: Only device data, no personal information or credentials
- **One-Time Submission**: Switch auto-turns off after submission to prevent accidental repeated sharing

### 🌐 Cloudflare Worker Infrastructure
- **Data Collection Service**: Secure endpoint for receiving debug submissions
- **Web Data Viewer**: Interactive interface for browsing submitted patterns
- **Pattern Discovery Framework**: Foundation for automated decoder improvements

### 📊 Enhanced Data Collection
- **Device Type Classification**: Captures functional device types (moisture_full, rain, etc.)
- **Complete Payload Data**: Raw hex strings for reverse engineering
- **Decoded Values**: Sensor readings for validation and comparison
- **Rich Metadata**: RSSI, battery level, firmware versions, device names

## 🔧 Technical Improvements

### Privacy-Conscious Design
- **Opt-In Only**: Users must explicitly toggle the debug switch
- **Anonymous Submissions**: No user identifiers, locations, or personal data
- **Rate Limiting**: Prevents abuse and ensures fair usage
- **Data Retention**: Automatic cleanup after 90 days

### User Experience
- **Simple Interface**: One-click data submission
- **Clear Feedback**: Success/error notifications
- **Transparent**: Users can view exactly what data is submitted
- **Control**: Users decide when and if to share data

## 📈 Community Benefits

### Pattern Discovery
- **New Device Support**: Discover patterns for unsupported device models
- **Firmware Variations**: Identify differences across device firmware versions
- **Decoder Accuracy**: Validate and improve decoder precision with real data
- **Edge Cases**: Find and fix unusual device behaviors

### Continuous Improvement
- **Real-World Validation**: Test decoders against actual device data
- **Crowdsourced Knowledge**: Leverage community device diversity
- **Future-Proofing**: Prepare for new device models and firmware updates

## 🛠️ Installation & Usage

### Existing Users
1. Update to v1.3.12 through HACS or manual installation
2. Restart Home Assistant
3. Look for "Submit Debug Data" switch in your HomGar entities
4. Toggle the switch to contribute anonymous device data

### New Users
1. Install integration through HACS or manual installation
2. Configure your HomGar/RainPoint account
3. Find the "Submit Debug Data" switch in your entities
4. Optionally contribute to improve decoder accuracy

## 🔒 Privacy Statement

This update collects **only** the following anonymous data:
- Device model numbers (e.g., HCS021FRF, HCS012ARF)
- Raw sensor payloads (hex strings)
- Decoded sensor values (temperature, humidity, etc.)
- Basic metadata (RSSI, battery, firmware)

**We DO NOT collect:**
- Personal information (names, emails, locations)
- Account credentials or tokens
- Device identifiers (MAC addresses, serial numbers)
- Usage patterns or timestamps

## 🌍 Data Viewer

Browse collected device patterns at:
[https://homgar-debug-worker.funkypeople.workers.dev/view](https://homgar-debug-worker.funkypeople.workers.dev/view)

- Filter by device model
- Copy raw payloads for analysis
- View decoded values and metadata
- Track community contributions

## 📋 Supported Devices

This release enhances support for all HomGar/RainPoint devices:
- HCS021FRF (Moisture + Temp + Lux)
- HCS012ARF (Rain Gauge)
- HCS026FRF (Moisture Only)
- HCS014ARF (Temperature + Humidity)
- HCS008FRF (Flowmeter)
- HCS0530THO (CO2 + Temp + Humidity)
- And all other supported models

## 🙏 Community Contribution

By participating in debug data submission, you're helping:
- Improve decoder accuracy for everyone
- Add support for new device models
- Fix firmware-specific issues
- Build a more robust integration

Thank you for contributing to the HomGar/RainPoint community!

---

**Version**: 1.3.12  
**Release Date**: March 29, 2026  
**Compatibility**: Home Assistant 2024.1+  
**License**: MIT
