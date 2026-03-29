# HomGar/RainPoint Cloud integration for Home Assistant

[![Release](https://img.shields.io/github/release/brettmeyerowitz/homeassistant-homgar.svg)](https://github.com/brettmeyerowitz/homeassistant-homgar/releases)
[![License](https://img.shields.io/github/license/brettmeyerowitz/homeassistant-homgar.svg)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Default-blue.svg)](https://github.com/hacs/integration)

Unofficial Home Assistant component for RainPoint Smart+ devices via HomGar cloud API.

**Important clarification:** HomGar is the mobile app/cloud platform, while RainPoint is the actual hardware manufacturer. All device models (HCS*, HTV*, etc.) are RainPoint hardware that can be accessed via either mobile app.

---

## Compatibility

This integration supports RainPoint Smart+ devices via HomGar cloud API. **Important clarification:**

### **HomGar vs RainPoint:**
- **HomGar**: The mobile app and cloud platform
- **RainPoint**: The actual hardware manufacturer and device models

**All device models (HCS*, HTV*, etc.) are RainPoint hardware** that can be accessed via either the HomGar or RainPoint mobile app.

### RainPoint Smart+ Devices:

| Device | Model | Capabilities |
|--------|-------|-------------|
| **Irrigation Display Hub** | HWS019WRF-V2 | Hub/controller |
| **Soil & Moisture Sensor** | HCS021FRF | Moisture + Temperature + Light |
| **High Precision Rain Sensor** | HCS012ARF | Rain (hourly/daily/weekly/total) |
| **Outdoor Air Humidity Sensor** | HCS014ARF | Temperature + Humidity |
| **2-Zone Water Timer** | HTV213FRF | Flow control |
| **Soil Moisture Probe (Simple)** | HCS026FRF | Moisture only |

All devices communicate via the HomGar cloud backend (`region3.homgarus.com`).

---

## Multiple Accounts & Sites

### **⚠️ Important: API Login Conflict**
**Logging in via this integration will log you out of the mobile app!** The HomGar/RainPoint API only allows one active session per account.

### **Solutions:**
1. **Separate API Account** (Recommended): Create a dedicated account for API access
2. **Multiple Accounts**: Use different accounts for mobile app vs integration
3. **Accept Limitation**: Re-login to mobile app after Home Assistant setup

### **Creating a Separate API Account:**
1. **Log out** from your main Homgar/RainPoint mobile app
2. **Create new account** with different email address
3. **Log back in** to your main account in mobile app
4. **Go to 'Me' → 'Home management' → your home → 'Members'**
5. **Invite the new API account** to your home
6. **Log into API account** and accept the invitation
7. **Use API account credentials** in Home Assistant

### **Multiple Login Support:**
You can add multiple HomGar/RainPoint accounts to Home Assistant, perfect for:

- **Multiple properties**: Different homes/sites with separate accounts
- **Both app types**: Use HomGar app for one site, RainPoint app for another
- **Separate credentials**: Different email/password combinations for various locations

### **Setup Multiple Accounts:**
1. **First Integration**: Add your primary account as described above
2. **Additional Accounts**: 
   - Go to **Settings → Devices & Services → Add Integration**
   - Search for **HomGar/RainPoint Cloud**
   - Enter credentials for the second account
   - Choose the appropriate app type for that account
   - Select homes for that specific account

### **Example Use Cases:**
- **Home + Vacation House**: HomGar account for home, RainPoint account for vacation property
- **Multiple Properties**: Separate RainPoint accounts for different rental properties
- **App Testing**: Both HomGar and RainPoint apps for the same location (different accounts)

### **Entity Naming with Multiple Accounts:**
Each account creates unique entities based on the app selection:
- `sensor.homgar_home_garden_moisture` (Homgar account)
- `sensor.rainpoint_vacation_garden_moisture` (RainPoint account)
- `sensor.homgar_rental1_soil_temperature` (Second Homgar account)

**Note**: Each integration instance is independent with its own update schedule and error handling.

---

## Features

- **Dual App Support**: Choose between HomGar or RainPoint app during setup
- **Optimized API Calls**: Efficient `multipleDeviceStatus` for all users
- **Hybrid API Strategy**: Automatic fallback to individual calls if needed
- Login with your HomGar/RainPoint account (email + area code)
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
- **Raw payload sensor** for each device (disabled by default) - useful for debugging
- **Automatic brand detection** - Devices show as "HomGar" or "RainPoint" manufacturer based on your app selection

---

## How Brand Detection Works

The integration automatically determines the device brand based on your app selection:

### **Important Understanding:**
- **HomGar**: Mobile app and cloud platform name
- **RainPoint**: Hardware manufacturer and device models

**All device models (HCS*, HTV*, etc.) are RainPoint hardware** that can be accessed via either mobile app.

### **App Selection → Brand Mapping:**
- **HomGar App** → Devices show as "HomGar" manufacturer in Home Assistant
- **RainPoint App** → Devices show as "RainPoint" manufacturer in Home Assistant

### **Technical Implementation:**
- Brand is determined by the `app_type` selected during setup
- Not based on device model detection (all models are RainPoint hardware)
- Ensures consistent branding that matches your mobile app choice
- Affects device names and entity IDs in Home Assistant

### **Example:**
If you select "RainPoint App" during setup:
- Device appears as: `"RainPoint HCS026FRF"`
- Entity ID: `sensor.rainpoint_92_cbd_garden_moisture`
- Entity name: `Garden Moisture`

If you select "HomGar App" during setup:
- Device appears as: `"HomGar HCS026FRF"`  
- Entity ID: `sensor.homgar_92_cbd_garden_moisture`
- Entity name: `Garden Moisture`

### **Entity Naming Pattern:**
**Format**: `sensor.{brand}_{home_name}_{device_name}`

**Components:**
- **{brand}**: `homgar` or `rainpoint` (from app selection)
- **{home_name}**: Slugified home name (e.g., `92_cbd`)
- **{device_name}**: Slugified device name (e.g., `garden_moisture`)

**Slugification Process:**
- Converts to lowercase
- Replaces non-alphanumeric characters with underscores
- Removes multiple consecutive underscores
- Ensures valid Home Assistant entity IDs

**Examples:**
- `sensor.homgar_my_home_garden_moisture`
- `sensor.rainpoint_vacation_house_rain_sensor`
- `sensor.homgar_greenhouse_temperature_humidity`

This ensures unique, descriptive entity IDs that reflect your app choice and home/device names.

---

## Upgrade and Migration

### For Existing Users (v1.0.0 and earlier)

If you're upgrading from a previous version of this integration:

**No action required for most users!** The integration will automatically:
- **Default to HomGar app type** for backward compatibility
- **Continue working** with your existing devices and settings
- **Maintain all current functionality**

### When to Reconfigure

Consider reconfiguring the integration if:
- You want to switch from HomGar to RainPoint app (or vice versa)
- You're not seeing your devices or getting empty data
- You want to take advantage of the app selection feature

### How to Reconfigure

1. Go to **Settings → Devices & Services → HomGar**
2. Click on your integration
3. Select **Configure** (or **Reconfigure**)
4. **Select your app type**:
   - **HomGar App**: Choose if you use the HomGar mobile app
   - **RainPoint App**: Choose if you use the RainPoint Smart+ mobile app
5. Complete the setup

**Important**: Choose the app you actually use on your phone to ensure you get access to your correct devices.

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

### Setup Process

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **HomGar/RainPoint Cloud**
3. **Select your app type**:
   - **HomGar App**: For HomGar app users
   - **RainPoint App**: For RainPoint Smart+ app users (recommended)
4. Enter your account credentials (email and area code)
5. Select which homes to include
6. Complete the setup

**⚠️ Important**: API login will log you out of the mobile app. Consider creating a separate API account for continuous mobile app access.

**Important**: The app selection determines which home/hub you get access to. Choose the app you actually use on your phone.

---

## Performance Optimizations

### Efficient API Calls
- **Optimized endpoint**: Uses `multipleDeviceStatus` to get all device statuses in a single request
- **Reduced server load**: Single API call instead of multiple individual calls
- **Faster updates**: All sensors update simultaneously
- **Universal compatibility**: Works for both HomGar and RainPoint users

### Hybrid Strategy
The integration automatically tries the optimized `multipleDeviceStatus` API first and falls back to individual calls if needed, ensuring maximum compatibility and efficiency.

**Note**: Both HomGar and RainPoint users benefit from the same efficient API calls. The app selection only determines which account credentials are used.

---

## Example manifest.json

Below is the manifest file for this integration (as of version 1.3.12):

```json
{
    "domain": "homgar",
    "name": "HomGar/RainPoint Cloud",
    "version": "1.3.12",
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

## Debugging with Raw Payload Sensor

Each device has a **Raw Payload** sensor (disabled by default) that shows the original hex data from the API. This is useful for debugging and troubleshooting.

### To enable the raw payload sensor:

1. Go to **Settings → Devices & Services → HomGar**
2. Click on a device
3. Find the "Raw Payload" sensor (it will be grayed out/disabled)
4. Click on it and select **Enable**
5. The sensor will now show the hex payload (e.g., `10#E1C600DC01881AFF...`)

This feature is particularly helpful when:
- Troubleshooting sensor values
- Reporting issues with new sensor models
- Comparing decoded values with the raw API data

---

## Reporting Unsupported Sensors

If you have a HomGar/RainPoint sensor that isn't supported yet, the integration will:

1. **Show a persistent notification** in Home Assistant with the sensor model and raw payload data
2. **Create a diagnostic entity** named `[Sensor Name] Unsupported ([Model])` with the raw payload in its attributes
3. **Log a warning** with full details to the Home Assistant logs

To help add support for your sensor:

1. Open the HomGar/RainPoint app on your phone and note the sensor values being displayed (e.g., temperature, humidity, battery level)
2. In Home Assistant, go to **Settings → Devices & Services → HomGar** and find the unsupported sensor entity
3. Click on the entity and copy the `raw_payload` attribute value
4. Open an issue at https://github.com/brettmeyerowitz/homeassistant-homgar/issues with:
   - Your sensor model (e.g., `HCS015ARF+`)
   - The raw payload data
   - **Screenshots or values from the mobile app** showing what the sensor is currently reading
   - This helps us decode the payload by matching the raw bytes to actual values

---

## Troubleshooting

### App Selection Issues
- **Wrong app selected**: Reconfigure the integration and choose the correct app (HomGar vs RainPoint)
- **No devices found**: Ensure you're selecting the app you actually use on your phone
- **Existing users**: If upgraded from previous version, you're automatically using HomGar app type. Reconfigure if you need RainPoint
- **Multiple accounts**: Each integration instance is independent. Check the correct integration for your specific site
- **Devices offline**: This may occur if devices are inactive or not reporting data

### API Login Issues
- **Logged out of mobile app**: API login conflicts with mobile app session
- **Solution**: Create separate API account or re-login to mobile app after setup
- **Multiple devices**: Each API login kicks other sessions off the account

### Performance Issues
- **Slow updates**: Check if you're using the correct app type for optimal performance
- **Rate limiting**: The integration automatically handles API rate limiting with appropriate delays

---

## Credits

This integration was developed by Brett Meyerowitz. It is not affiliated with HomGar.

**Special thanks to [shaundekok/rainpoint](https://github.com/shaundekok/rainpoint) for Node-RED flow inspiration, payload decoding, and entity mapping logic.**

Feedback and contributions are welcome!
