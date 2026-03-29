# HomGar/RainPoint Cloud Integration v1.3.13

## 🔧 Critical Bug Fixes for HTV213FRF

This release resolves critical issues reported in Issue #11 affecting HTV213FRF valve controller devices.

## ✅ Issues Fixed

### 🎯 HTV213FRF Hub Online Detection
- **Problem**: Valve entities showing as "unavailable" due to hub_online=False
- **Root Cause**: Decoder expected 0x01 but device uses 0xDC pattern
- **Solution**: Added support for 0xDC hub online pattern
- **Result**: ✅ Valve entities now become available

### 🎯 HTV213FRF Zone Numbering
- **Problem**: Zones 25, 33, 34, 41, 173 instead of expected zones 1, 2
- **Root Cause**: Using raw zone IDs instead of sequential numbering
- **Solution**: Map raw zone IDs to sequential numbers (1,2,3,4,5)
- **Result**: ✅ User-friendly zone numbering

## 📊 Technical Improvements

### 🔍 Enhanced Logging
- **INFO-level logging** for HTV213FRF troubleshooting (no debug mode needed)
- **Zone detection details** showing raw IDs and mapping
- **Hub state analysis** with multiple pattern support
- **State change tracking** for zone transitions

### 🎛️ Hub State Detection
- **Multiple patterns supported**: 0x01 (standard), 0xDC (HTV213FRF)
- **Automatic pattern recognition** based on device type
- **Comprehensive logging** of hub state detection process

### 🗺️ Zone Mapping
- **Sequential numbering**: Zones 1,2,3,4,5 instead of raw IDs
- **Raw ID preservation**: Original zone IDs stored in debug info
- **State tracking**: Open/closed states and duration monitoring

## 🧪 Testing Requested

### 📱 Mobile App Screenshots
Please share screenshots of your HomGar app showing:
- Main device screen with both zones
- Zone 1 details (ON and OFF states)
- Zone 2 details (ON and OFF states)

### 🔄 Zone State Testing
1. Turn Zone 1 ON → Wait 30s → Check HA entities
2. Turn Zone 1 OFF → Wait 30s → Check HA entities
3. Turn Zone 2 ON → Wait 30s → Check HA entities
4. Turn Zone 2 OFF → Wait 30s → Check HA entities

### 📋 Log Sharing
Enhanced logging automatically captures zone changes without debug mode. Please share HA logs after testing.

## 🎯 Expected Results

### ✅ After Installation
- **Valve entities**: Available (not unavailable)
- **Zone numbering**: 1,2,3,4,5 (not 25,33,34,41,173)
- **Hub state**: Online detection working
- **State changes**: Captured in logs automatically

### 🔄 Still Needs Testing
- **Zone mapping**: Which HA zone corresponds to which physical zone
- **Zone count**: Should we filter to only show 2 zones instead of 5?

## 📁 Files Changed

- `custom_components/homgar/homgar_api.py` - HTV213FRF decoder improvements
- `custom_components/homgar/manifest.json` - Version 1.3.13
- `custom_components/homgar/const.py` - Version 1.3.13
- `CHANGELOG.md` - v1.3.13 entry
- `README.md` - Updated version reference

## 🚀 Installation

1. Update through HACS or manual installation
2. Restart Home Assistant
3. Check that valve entities are now available
4. Follow testing instructions above

## 🙏 Community Contribution

Your testing will help perfect the HTV213FRF decoder and improve support for all users with similar devices!

---

**Version**: 1.3.13  
**Release Date**: March 29, 2026  
**Compatibility**: Home Assistant 2024.1+  
**License**: MIT
