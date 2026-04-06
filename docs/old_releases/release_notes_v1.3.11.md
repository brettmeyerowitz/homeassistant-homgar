# HomGar/RainPoint Cloud Integration v1.3.11

## 🐛 Critical Bug Fixes

This release fixes critical import errors that prevented the integration from loading in Docker environments.

### 🔧 Bug Fixes
- **Fixed critical ImportError** that prevented integration from loading in Docker
- **Added missing BRAND_MAPPING** to const.py
- **Fixed VERSION import** in coordinator.py (was importing from wrong module)
- **Resolved all import errors** that caused integration to fail

### ✅ Docker Testing Validation
- **Validated integration in Docker environment** before release
- **Confirmed exact RainPoint parsing works** in production Docker
- **Verified versioned debug messages** display correctly
- **Tested real device data processing** in container

### 📋 Process Improvement
- **Added Docker testing to release workflow** (CRITICAL)
- **ALWAYS test in Docker before any release**
- **Prevents import errors from reaching production**

### 🎯 Docker Test Results
- ✅ Integration loads successfully without errors
- ✅ `[HomGar v1.3.11]` debug messages working
- ✅ Real sensor data being processed (HCS021FRF, HCS012ARF, HCS026FRF)
- ✅ Exact RainPoint C0527C.a() parsing method functional

### 🔍 Real Device Data in Docker
```
HCS021FRF (Bottom Garden): moisture=29%, temp=20.5°C, lux=1635.7
HCS012ARF (Rain Sensor): rain_last_7d=188.0mm
HCS026FRF (Top Garden): moisture sensor active
```

### 🚀 Installation
```bash
# Install via HACS or download the latest release
# Restart Home Assistant after installation
```

### 🐛 Troubleshooting
If you encounter issues:
1. Enable debug logging: `logger: custom_components.homgar: debug`
2. Check logs for `[HomGar v1.3.11]` prefixed messages
3. Report issues with debug logs included

### ⚠️ Important Note
This release fixes the broken v1.3.10 release that had import errors preventing the integration from loading. All users should update to v1.3.11.

---

**Full Changelog**: See [CHANGELOG.md](https://github.com/brettmeyerowitz/homeassistant-homgar/blob/main/CHANGELOG.md) for complete history.
