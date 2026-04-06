# HomGar/RainPoint Cloud Integration v2.0.3

## 🆕 New Device Support

### HTV0542FRF 4-Zone Valve Controller

We're excited to announce support for the **HTV0542FRF 4-zone RF irrigation timer**! This device is now fully supported with zone state detection and hub online monitoring.

**Key Features:**
- ✅ **4-zone valve control** - All zones detected and monitored
- ✅ **Zone state detection** - Open/closed status for each zone
- ✅ **Hub online monitoring** - Connection status tracking
- ✅ **RSSI signal strength** - Monitor RF signal quality
- ✅ **Consistent valve logic** - Uses same bit 0 state detection as other valve controllers

## 🎯 Issue Resolution

- **Issue #22**: HTV0542FRF 4-zone irrigation timers now fully supported

## 📝 Technical Details

### Decoder Implementation

The HTV0542FRF decoder was implemented based on payload analysis and device specifications:

- **Fixed-record format** (not TLV like HTV0540FRF)
- **Zone IDs**: 0x19 (zone 1), 0x1A (zone 2), 0x1B (zone 3), 0x1C (zone 4)
- **State detection**: Bit 0 of state byte (0=closed, 1=open)
- **Hub status**: 0x18 marker followed by 0x01 or 0xDC indicates online
- **4-zone configuration** based on device specifications

### Enhanced Logging

The decoder includes detailed logging for debugging:
- Zone-by-zone state reporting
- Hub online/offline detection
- RSSI signal strength monitoring
- Raw byte values for troubleshooting

## 🔧 What's Changed

### Modified Files
- `custom_components/homgar/api/decoders.py` - New HTV0542FRF decoder
- `custom_components/homgar/api/__init__.py` - Decoder exports
- `custom_components/homgar/homgar_api.py` - Backward compatibility
- `custom_components/homgar/const.py` - Model constant
- `custom_components/homgar/coordinator.py` - Decoder mapping
- `custom_components/homgar/manifest.json` - Version 2.0.3
- `CHANGELOG.md` - Release notes
- `README.md` - Version reference

## 📦 Installation

### HACS (Recommended)
1. Open HACS in Home Assistant
2. Go to Integrations
3. Find "HomGar/RainPoint Cloud"
4. Click "Update" to install v2.0.3

### Manual Installation
1. Download the latest release
2. Copy `custom_components/homgar` to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## 🧪 Testing

This release has been validated with:
- ✅ Real HTV0542FRF payload from Issue #22
- ✅ All 4 zones detected correctly
- ✅ Hub online status working
- ✅ Docker integration test passed
- ✅ No import errors or runtime issues

## 📊 Device Support Status

The integration now supports **40+ RainPoint/HomGar device models**, including:

**Valve Controllers:**
- HTV0540FRF (Multi-zone valve hub)
- HTV213FRF (2-zone irrigation timer)
- HTV245FRF (4-zone irrigation valve)
- **HTV0542FRF (4-zone RF irrigation timer)** ⭐ NEW

**Sensors:**
- Moisture sensors (HCS021FRF, HCS026FRF, etc.)
- Temperature/humidity sensors
- Rain gauges
- Flow meters
- Pool temperature sensors
- And many more...

## 🙏 Thank You

Special thanks to the user who reported Issue #22 and provided the payload sample that made this implementation possible!

## 🐛 Known Limitations

- Duration encoding requires more payload samples to fully decode
- Additional features may be refined as more users test the device

If you have an HTV0542FRF and can provide payload samples with different zone states (some open, some closed), please share them in Issue #22 to help improve the decoder!

---

**Full Changelog**: https://github.com/brettmeyerowitz/homeassistant-homgar/blob/main/CHANGELOG.md
