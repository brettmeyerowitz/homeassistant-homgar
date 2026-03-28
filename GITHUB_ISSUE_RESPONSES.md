# GitHub Issue Responses for v1.1.0

Copy and paste these responses to the corresponding GitHub issues.

---

## Issue #11, #9, #10 - Valve Support (HTV213FRF, HTV245FRF)

Excellent news! 🎉

I've just released **v1.2.0** with full valve support for **HTV0540FRF** (based on PR #7 by @gavinwoolley)! This includes:
- ✅ Valve entities (open/close control per zone)
- ✅ Duration number entities (1-60 min per zone)
- ✅ Dynamic zone detection (supports any number of zones)
- ✅ Immediate state reflection after commands

**For HTV213FRF and HTV245FRF users:**

Your models are similar to HTV0540FRF. Please upgrade to v1.2.0 and test:

1. **Update to v1.2.0** via HACS
2. **Restart Home Assistant**
3. **Check if your valve devices work**

If your HTV213FRF/HTV245FRF devices don't work with v1.2.0, they may use a different payload format. Please provide payload data using:
https://github.com/brettmeyerowitz/homeassistant-homgar/blob/main/DEBUG_VALVE_PAYLOAD.md

Let me know how it goes!

---

## Issue #12 - HCS021FRF Unavailable

Hi @deanpomerleau,

I've released **v1.1.0** with improved UI and better error handling. Please upgrade and test:

**To upgrade:**
1. Update to v1.1.0 via HACS
2. Restart Home Assistant
3. Check if sensors now show data

If still unavailable, please enable debug logging and share the logs:

Add to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.homgar: debug
```

Then restart and check logs for the raw payload from your HCS021FRF device. This will help diagnose if it's a decoding issue or if the device isn't reporting data.

---

## Issue #2 - Disconnection

Hi @arminreiss1966-sudo,

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
