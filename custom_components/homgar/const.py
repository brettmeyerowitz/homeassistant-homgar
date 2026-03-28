# Display Hub model constant
DOMAIN = "homgar"

CONF_AREA_CODE = "area_code"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_HIDS = "hids"  # list of selected home IDs
CONF_APP_TYPE = "app_type"  # "homgar" or "rainpoint"

DEFAULT_SCAN_INTERVAL = 120  # seconds

# Config entry data keys
CONF_TOKEN = "token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN_EXPIRES_AT = "token_expires_at"

# App type mappings
APP_TYPE_HOMGAR = "homgar"
APP_TYPE_RAINPOINT = "rainpoint"
APP_CODE_MAPPING = {
    APP_TYPE_HOMGAR: "1",
    APP_TYPE_RAINPOINT: "2",
}

# Known models
MODEL_MOISTURE_SIMPLE = "HCS026FRF"  # Moisture only
MODEL_MOISTURE_FULL = "HCS021FRF"    # Moisture + temp + lux
MODEL_RAIN = "HCS012ARF"             # Rain gauge
# Additional models from Node-RED flow
MODEL_TEMPHUM = "HCS014ARF"          # Temperature/Humidity
MODEL_FLOWMETER = "HCS008FRF"        # Flowmeter
MODEL_CO2 = "HCS0530THO"             # CO2/Temp/Humidity
MODEL_POOL = "HCS0528ARF"            # Pool/Temperature
MODEL_POOL_PLUS = "HCS015ARF+"       # Pool + Ambient temp/humidity
MODEL_DISPLAY_HUB = "HWS019WRF-V2"   # Smart+ Irrigation Display Hub

# === HCS Sensor Series (v1.3.0) ===

# Moisture-only sensors
MODEL_HCS005FRF = "HCS005FRF"        # Moisture-only sensor
MODEL_HCS003FRF = "HCS003FRF"        # Moisture-only sensor

# Multi-sensors (temp + moisture + lux)
MODEL_HCS024FRF_V1 = "HCS024FRF-V1"  # Multi-sensor (temp+moisture+lux)
MODEL_HCS044FRF = "HCS044FRF"        # Multi-sensor device
MODEL_HCS666FRF = "HCS666FRF"        # Sensor variant (similar to HCS021FRF)
MODEL_HCS666RFR_P = "HCS666RFR-P"    # Sensor variant with plus features
MODEL_HCS999FRF = "HCS999FRF"        # Advanced sensor variant
MODEL_HCS999FRF_P = "HCS999FRF-P"    # Advanced sensor variant with plus features
MODEL_HCS666FRF_X = "HCS666FRF-X"    # Extended sensor variant

# Temperature/Humidity sensors
MODEL_HCS027ARF = "HCS027ARF"        # Temperature/humidity sensor
MODEL_HCS016ARF = "HCS016ARF"        # Temperature/humidity sensor
MODEL_HCS701B = "HCS701B"            # Wall-mounted sensor
MODEL_HCS596WB = "HCS596WB"          # Weather station base
MODEL_HCS596WB_V4 = "HCS596WB-V4"    # Weather station base v4
MODEL_HCS706ARF = "HCS706ARF"        # Environmental sensor
MODEL_HCS802ARF = "HCS802ARF"        # Environmental sensor
MODEL_HCS048B = "HCS048B"            # Compact sensor device
MODEL_HCS888ARF_V1 = "HCS888ARF-V1"  # Multi-function sensor v1
MODEL_HCS0600ARF = "HCS0600ARF"      # Advanced environmental sensor

# Pool temperature sensors
MODEL_HCS015ARF = "HCS015ARF"        # Pool temperature sensor
MODEL_HCS0528ARF = "HCS0528ARF"      # Pool temperature sensor

# === Valve Controllers (v1.2.0) ===
MODEL_VALVE_213 = "HTV213FRF"        # Single-zone RF irrigation timer (similar to HTV0540FRF)
MODEL_VALVE_245 = "HTV245FRF"        # Irrigation valve (similar to HTV0540FRF)
MODEL_VALVE_HUB = "HTV0540FRF"       # Multi-zone valve hub (fully supported)
