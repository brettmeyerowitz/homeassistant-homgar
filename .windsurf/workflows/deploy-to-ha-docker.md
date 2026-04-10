---
description: Deploy integration to the ha-test Docker container for testing
---

## Deploy and restart

// turbo
```
docker cp custom_components/homgar ha-test:/config/custom_components/ && docker restart ha-test
```

## Wait for startup and confirm connected

// turbo
```
sleep 25 && docker logs ha-test --since=27s 2>&1 | grep -v DEBUG | grep -E "connected successfully|subscribeStatus|Found.*devices|forcing fresh login"
```

## Watch MQTT valve updates live

// turbo
```
docker logs ha-test -f 2>&1 | grep -E "MQTT update|coordinator_mqtt|sub_devices|Updated sensor|Decoded valve"
```

## Key rules
- **Always test inside the `ha-test` Docker container — never locally**
- The container is named `ha-test`
- After copying files, always restart the container to clear `.pyc` cache
- HomGar account uses `homgar` app_type; RainPoint account uses `rainpoint` app_type — never mix credentials
- MQTT uses `securemode=2` with a fresh HMAC-SHA1 timestamp on every connect
- Subscribe only to 5 `/sys/` topics — no wildcards, no `/user/` topics (causes `rc=7` disconnect)

## MQTT Device Support

**How it works:** MQTT connects at the **hub level** (virtual device), receiving updates for **ALL** sub-devices (D01, D02, etc.) in format: `#P{timestamp}|{hub_mid}|{D01: {...}, D02: {...}}|...`

| Device Type | Real-time MQTT | REST Polling | Notes |
|-------------|----------------|--------------|-------|
| **Valves** (HTV113FRF, HTV213FRF, etc.) | ✅ Yes | ✅ 30s backup | Valve state changes pushed instantly |
| **Flow Meters** (HCS008FRF) | ❓ Unknown | ✅ 30s primary | May not send MQTT; requires live testing |
| **Sensors** (moisture, temp/hum, rain) | ❓ Unknown | ✅ 30s primary | Likely REST-only |

**To verify MQTT support for a device:**
```
docker logs ha-test -f 2>&1 | grep -E "MQTT update.*D[0-9]+" | grep <device_addr>
```

**Key insight:** The code supports MQTT for ANY sub-device with a decoder in `DECODER_REGISTRY`, but the HomGar hub may only send MQTT messages for valve state changes (not sensors).
