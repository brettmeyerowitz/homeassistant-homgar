# GitHub Issue Responses for v1.3.0

Copy and paste these responses to the corresponding GitHub issues.

---

## Issue #12 - HCS021FRF Unavailable

Hi @deanpomerleau,

Great news! 🎉 I've just released **v1.3.0** which addresses the HCS021FRF unavailable issue:

### What's Fixed:
- ✅ **Decoder implementation verified** against official Android app protocol specification
- ✅ **Enhanced payload validation** with `_validate_tag()` and `_validate_payload()` helpers
- ✅ **Better error handling** - shows exact byte positions where validation fails
- ✅ **Comprehensive logging** for troubleshooting device connectivity vs decoder issues

### What to Do:
1. **Update to v1.3.0** via HACS
2. **Restart Home Assistant**
3. **Check if your HCS021FRF now shows data**

### If Still Unavailable:
The decoder is now verified correct against the official protocol. If you still see "unavailable", it's likely a device connectivity issue rather than a decoder problem. Please enable debug logging:

```yaml
logger:
  default: info
  logs:
    custom_components.homgar: debug
```

The debug logs will show:
- Whether the device is reporting data to the API
- Raw payload data if received
- Exact validation errors (if any)

This will help determine if it's a device/API issue vs decoder issue.

Let me know how v1.3.0 works for you!

---

## Issue #8 - Garbled Hub Values

Hi @deanpomerleau,

I've released **v1.3.0** with improvements for display hub debugging:

### What's Improved:
- ✅ **Enhanced error handling** across all decoders
- ✅ **Better logging** for troubleshooting display hub issues
- ✅ **Standardized validation patterns** to catch payload format issues

### What to Do:
1. **Update to v1.3.0** via HACS
2. **Restart Home Assistant**
3. **Enable debug logging** to capture detailed information:

```yaml
logger:
  default: info
  logs:
    custom_components.homgar: debug
```

The enhanced logging will help identify:
- Whether the display hub is sending data
- What payload format it's using
- Any validation errors in the decoding process

Please share the debug logs if the garbled values persist - this will help determine if we need a specific decoder for your display hub model.

---

## Issue #11, #9, #10 - Valve Support (HTV213FRF, HTV245FRF)

Excellent news! 🎉

I've just released **v1.3.0** with even better valve support! Building on the v1.2.0 improvements:

### What's New in v1.3.0:
- ✅ **Refactored decoder architecture** - cleaner, more maintainable
- ✅ **Enhanced error handling** for better debugging
- ✅ **Comprehensive logging** throughout the valve control process
- ✅ **Unified constant naming** for better code organization

### Valve Support Status:
- ✅ **HTV0540FRF** - Full support (valve entities + duration control)
- ⚠️ **HTV213FRF, HTV245FRF** - Should work with HTV0540FRF decoder (similar protocol)

### For HTV213FRF/HTV245FRF Users:
Please upgrade to v1.3.0 and test your valve devices. If they don't work, the enhanced logging will help identify any protocol differences.

### To Upgrade:
1. Update to v1.3.0 via HACS
2. Restart Home Assistant
3. Test your valve entities

Let me know how the v1.3.0 improvements work for your setup!

---

## General Response Template for Other Issues

Hi 👋,

I've just released **v1.3.0** with major improvements that may help with your issue:

### What's New in v1.3.0:
- 🆕 **30+ new device decoders** - supports more HomGar/RainPoint devices
- 🔧 **Refactored decoder architecture** - cleaner, more reliable
- 📊 **Enhanced error handling** - better debugging information
- 🏗️ **Decoder registry pattern** - more maintainable code
- 📝 **Comprehensive logging** - easier troubleshooting

### What to Do:
1. **Update to v1.3.0** via HACS
2. **Restart Home Assistant**
3. **Test your devices**

If your issue persists, please enable debug logging:

```yaml
logger:
  default: info
  logs:
    custom_components.homgar: debug
```

The enhanced logging in v1.3.0 will provide much more detailed information to help diagnose any remaining issues.

Let me know how v1.3.0 works for you!

I've released **v1.1.0** with improved error handling and UI enhancements.

**To update and reconfigure:**
1. **Update to v1.1.0** via HACS
2. **Delete the existing integration:**
   - Settings → Devices & Services
   - Find "HomGar/RainPoint Cloud"
   - Click three dots → Delete
3. **Re-add the integration:**
   - Settings → Devices & Services → Add Integration
   - Search for "HomGar" or "RainPoint"
   - Select correct app type
   - Enter credentials

The new version has better token management and should maintain connection reliably.

Let me know if you still experience disconnections!

---

## Issue #4 - Device Classes and Flowmeter Decoding

Hi @fredi-e,

Good news! Device classes are fully implemented and v1.1.0 adds visual improvements:

✅ **All sensors have proper device classes** (moisture, temperature, humidity, etc.)
✅ **Icons added** for better visual identification
✅ **Diagnostic entities** properly categorized

**Update to v1.1.0** via HACS to get the improved UI with icons!

If you have specific flowmeter decoding improvements in mind, please let me know what you'd like to see.

---

## Issue #8 - Garbled Hub Values

Hi @deanpomerleau,

I've released **v1.1.0** with UI improvements. Please upgrade and let me know if the garbled values persist.

If still seeing garbled data, please provide:
1. **Which specific entities** show garbled data?
2. **Screenshot or example** of the garbled values
3. **Expected values** (from mobile app)

Also enable debug logging to capture the raw payload - this will help identify the decoding issue.

Add to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.homgar: debug
```

---

## General Instructions for All Users

**v1.1.0 Changelog:**
- Added icons for all sensor types
- Raw payload sensors marked as diagnostic (disabled by default)
- Recognized valve models: HTV213FRF, HTV245FRF, HTV0540FRF
- All devices correctly branded as RainPoint hardware
- Better error messages and logging

**How to Update:**
1. Open HACS in Home Assistant
2. Find "HomGar/RainPoint Cloud"
3. Click "Update" or "Redownload"
4. Restart Home Assistant

**Need Help?**
- Check the CHANGELOG: https://github.com/brettmeyerowitz/homeassistant-homgar/blob/main/CHANGELOG.md
- For valve support: https://github.com/brettmeyerowitz/homeassistant-homgar/blob/main/DEBUG_VALVE_PAYLOAD.md
- Open a new issue if problems persist
