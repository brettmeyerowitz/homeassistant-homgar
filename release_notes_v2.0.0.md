# HomGar/RainPoint v2.0.0 - Real-time MQTT Support

## 🚀 Major New Features

### Real-time MQTT Support
- **Instant valve state updates** - No more 2-minute polling delay!
- **Alibaba Cloud IoT Platform integration** for push notifications
- **Automatic connection** when MQTT credentials available
- **Graceful fallback** to REST API polling if MQTT unavailable

### Enhanced Valve Control
- Real-time feedback when opening/closing valves
- Immediate state updates in Home Assistant
- Better user experience for irrigation control

## 🔧 Critical Bug Fixes

### Valve State Detection (Issue #11)
- **Fixed HTV213FRF/HTV245FRF valve state** - valves now correctly show closed when off
- **Corrected bit 0 logic** for ASCII format valve state (matching TLV format from PR #7)
- All observed closed states (0, 6, 30, 146, 680) now correctly interpreted
- **Resolves Issue #11** - Dean's valves no longer always show "on"

## 📊 Technical Improvements

- MQTT client with automatic reconnection and error handling
- Enhanced debug logging for valve operations (extensive logs for troubleshooting)
- MQTT credentials automatically extracted from login response
- Thread-safe MQTT message handling with async coordinator updates
- Based on proven implementation from [tao-irrigation](https://github.com/martinpeniak/tao-irrigation) project

## ⚠️ Breaking Changes

### New Dependency
- **Requires `paho-mqtt>=1.6.0`** (automatically installed by Home Assistant)
- Users will need to **restart Home Assistant** after update to install new dependency

### Integration Type Change
- Changed from `cloud_polling` to `cloud_push`
- MQTT provides real-time updates when available
- Falls back to polling if MQTT not available or credentials missing

## 🧪 Testing

- ✅ Docker tested with real device data
- ✅ MQTT connection verified with Alibaba Cloud IoT Platform
- ✅ Valve state fix confirmed with Dean's log data
- ✅ All existing sensors continue to work
- ✅ Graceful fallback tested when MQTT unavailable

## 📝 Installation Notes

1. Update the integration through HACS or manually
2. **Restart Home Assistant** to install paho-mqtt dependency
3. MQTT will automatically connect if credentials are available
4. Check logs for "HomGar: MQTT client connected successfully" message
5. Integration falls back to polling if MQTT unavailable

## 🎯 For Dean (Issue #11)

Your HTV213FRF/HTV245FRF valves should now:
- ✅ Show correct closed state when off (not always "on")
- ✅ Update in real-time when you control them (if MQTT available)
- ✅ Work with extensive debug logging for troubleshooting

Please test and share logs if you encounter any issues!

## 📚 Documentation

- MQTT authentication uses Alibaba Cloud IoT Platform (securemode=3, hmacsha1)
- MQTT topic: `/sys/{productKey}/{deviceName}/thing/service/property/set`
- Credentials extracted from login response automatically
- No configuration needed - works out of the box

## 🙏 Credits

MQTT implementation based on the excellent work from [martinpeniak/tao-irrigation](https://github.com/martinpeniak/tao-irrigation).
