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

# Valve models (recognized but not yet fully supported - need payload data)
MODEL_VALVE_213 = "HTV213FRF"        # Single-zone RF irrigation timer
MODEL_VALVE_245 = "HTV245FRF"        # Irrigation valve
MODEL_VALVE_HUB = "HTV0540FRF"       # Multi-zone valve hub
