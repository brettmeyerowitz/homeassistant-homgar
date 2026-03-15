# HomGar Cloud integration for Home Assistant

Unofficial Home Assistant component for HomGar Cloud, supporting RF soil moisture and rain sensors via the HomGar cloud API.

---

## Compatibility

Tested with:
- Hub: `HWG023WBRF-V2`
- Soil moisture probes:
  - `HCS026FRF` (moisture-only)
  - `HCS021FRF` (moisture + temperature + lux)
- Rain gauge:
  - `HCS012ARF`
- Temperature/Humidity:
  - `HCS014ARF`
- Flowmeter:
  - `HCS008FRF`
- CO2/Temperature/Humidity:
  - `HCS0530THO`
- Pool/Temperature:
  - `HCS0528ARF`
- Pool + Ambient temp/humidity:
  - `HCS015ARF+`

The integration communicates with the same cloud endpoints as the HomGar app (`region3.homgarus.com`).

---

## Features

- Login with your HomGar account (email + area code)
- Select which homes to include
- Auto-discovers supported sub-devices
- Exposes:
  - Moisture %
  - Temperature (where applicable)
  - Illuminance (HCS021FRF)
  - Rain:
    - Last hour
    - Last 24 hours
    - Last 7 days
    - Total rainfall
  - Temperature/Humidity (HCS014ARF)
  - Flowmeter readings (HCS008FRF)
  - CO2, temperature, humidity (HCS0530THO)
  - Pool temperature (HCS0528ARF)
  - Pool + ambient temperature and humidity (HCS015ARF+)
- Attributes:
  - `rssi_dbm`
  - `battery_status_code`
  - `last_updated` (cloud timestamp)

---

## Installation

### Easy Installation via HACS

You can quickly add this repository to HACS by clicking the button below:

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=brettmeyerowitz&repository=homeassistant-homgar&category=integration)

#### Manual Installation

1. Copy the `custom_components/homgar` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

---

## Configuration

Go to **Settings → Devices & Services → Add Integration** and search for **HomGar Cloud**. Enter your HomGar account credentials (email and area code) to connect.

---

## Example manifest.json

Below is the manifest file for this integration (as of version 0.2.6):

```json
{
    "domain": "homgar",
    "name": "HomGar Cloud",
    "version": "0.2.6",
    "documentation": "https://github.com/brettmeyerowitz/homeassistant-homgar",
    "issue_tracker": "https://github.com/brettmeyerowitz/homeassistant-homgar/issues",
    "requirements": [],
    "codeowners": [
        "@brettmeyerowitz"
    ],
    "config_flow": true,
    "iot_class": "cloud_polling",
    "integration_type": "hub",
    "loggers": [
        "custom_components.homgar"
    ]
}
```

---

## Reporting Unsupported Sensors

If you have a HomGar sensor that isn't supported yet, the integration will:

1. **Show a persistent notification** in Home Assistant with the sensor model and raw payload data
2. **Create a diagnostic entity** named `[Sensor Name] Unsupported ([Model])` with the raw payload in its attributes
3. **Log a warning** with full details to the Home Assistant logs

To help add support for your sensor:

1. Open the HomGar app on your phone and note the sensor values being displayed (e.g., temperature, humidity, battery level)
2. In Home Assistant, go to **Settings → Devices & Services → HomGar** and find the unsupported sensor entity
3. Click on the entity and copy the `raw_payload` attribute value
4. Open an issue at https://github.com/brettmeyerowitz/homeassistant-homgar/issues with:
   - Your sensor model (e.g., `HCS015ARF+`)
   - The raw payload data
   - **Screenshots or values from the HomGar app** showing what the sensor is currently reading
   - This helps us decode the payload by matching the raw bytes to actual values

---

## Credits

This integration was developed by Brett Meyerowitz. It is not affiliated with HomGar.

**Special thanks to [shaundekok/rainpoint](https://github.com/shaundekok/rainpoint) for Node-RED flow inspiration, payload decoding, and entity mapping logic.**

Feedback and contributions are welcome!
