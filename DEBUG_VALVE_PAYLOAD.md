# Debug Instructions for Valve Devices (HTV213FRF/HTV245FRF)

To help add support for your valve device, we need to capture the raw payload data.

## Method 1: Enable Debug Logging in Home Assistant

1. **Add to your `configuration.yaml`:**
```yaml
logger:
  default: info
  logs:
    custom_components.homgar: debug
```

2. **Restart Home Assistant**

3. **Check your logs** (Settings → System → Logs) for entries like:
```
DEBUG (MainThread) [custom_components.homgar.coordinator] Processing hub mid=XXXXX with status
```

4. **Find the raw payload** for your valve device - it will look like:
```
{"id": "D01", "time": 1774648627320, "value": "10#E1C700DC01881DFF0F587DF718"}
```

5. **Copy the entire value** (the hex string after `10#`)

## Method 2: Use Developer Tools

1. **Go to Developer Tools → States**
2. **Find your valve device** (it might show as "Unsupported" or have a raw payload sensor)
3. **Look for the raw_payload attribute**
4. **Copy the hex value**

## What to Provide

Please provide the following information in your GitHub issue:

1. **Device Model**: HTV213FRF or HTV245FRF
2. **Raw Payload** (hex string): `E1C700DC01881DFF0F587DF718` (example)
3. **Device State** when payload was captured:
   - Is the valve open or closed?
   - What is the configured run duration?
   - Any other settings visible in the app?

4. **Multiple Payloads** if possible:
   - Payload when valve is CLOSED
   - Payload when valve is OPEN
   - Payload with different duration settings

## Example Format

```
Device: HTV213FRF
State: Valve CLOSED, Duration: 30 minutes
Payload: E1C700DC01881DFF0F587DF718

State: Valve OPEN, Duration: 30 minutes  
Payload: E1C800DC01881DFF0F587DF718

State: Valve CLOSED, Duration: 60 minutes
Payload: E1C700DC01881DFF0F587DF719
```

This will help us understand the payload format and add proper support for your device!
