# HomGar/RainPoint Cloud Integration v1.3.8

## 🎉 Enhanced Debug Experience

This release focuses on improving the debugging experience for users and developers by adding version information to all debug messages.

### 🐛 Bug Fixes
- **Fixed debug message versioning**
  - Add VERSION constant and debug_with_version helper to const.py
  - Update key debug messages in coordinator.py to include version info
  - Update HTV213FRF decoder debug messages with versioning
  - Import debug_with_version in homgar_api.py for consistent logging

### 🔧 Improvements
- **Enhanced debugging experience**
  - All debug messages now include integration version prefix
  - Easier troubleshooting for users and developers
  - Better identification of which integration version is generating logs

### 📚 Technical Details
- Added `VERSION = "1.3.8"` constant in `const.py`
- Added `debug_with_version()` helper function for consistent versioned logging
- Updated `_LOGGER.debug()` calls in `coordinator.py` to use versioned messages
- Updated HTV213FRF decoder debug messages in `homgar_api.py`
- Improved traceability in debug logs

### 🎯 Debug Message Format
Debug messages now appear as:
```
[HomGar v1.3.8] Processing hub mid=12345 with status
[HomGar v1.3.8] HTV213FRF decoded: 5 zones, hub_online=true
[HomGar v1.3.8] Decoded data for mid=12345 addr=1: {...}
```

### 📝 Previous Fixes Included
This build also includes all the fixes from v1.3.7:
- ✅ **HCS decoder payload length fixes** - Flexible parsing for shorter payloads
- ✅ **Shaun's HCS0530THO sensor working** - No more "Payload too short" errors
- ✅ **Real RainPoint implementation alignment** - Dynamic parsing approach confirmed

### 🚀 Installation
```bash
# Install via HACS or download the latest release
# Restart Home Assistant after installation
```

### 🐛 Troubleshooting
If you encounter issues:
1. Enable debug logging: `logger: custom_components.homgar: debug`
2. Check logs for `[HomGar v1.3.8]` prefixed messages
3. Report issues with debug logs included

### 🙏 Thanks
Special thanks to Shaun for testing and providing real device data that helped confirm our flexible decoder approach matches the actual RainPoint implementation!

---

**Full Changelog**: See [CHANGELOG.md](https://github.com/brettmeyerowitz/homeassistant-homgar/blob/main/CHANGELOG.md) for complete history.
