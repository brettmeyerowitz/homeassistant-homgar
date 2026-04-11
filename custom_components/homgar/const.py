# Display Hub model constant
DOMAIN = "homgar"
NAME = "HomGar/RainPoint Cloud"
VERSION = "3.0.1"

# Helper function for debug messages with version
def debug_with_version(message: str) -> str:
    """Format debug message with integration version."""
    return f"[HomGar v{VERSION}] {message}"

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
CONF_MQTT_PRODUCT_KEY = "mqtt_product_key"
CONF_MQTT_DEVICE_NAME = "mqtt_device_name"
CONF_MQTT_DEVICE_SECRET = "mqtt_device_secret"
CONF_MQTT_HOST = "mqtt_host"

# App type mappings
APP_TYPE_HOMGAR = "homgar"
APP_TYPE_RAINPOINT = "rainpoint"
APP_CODE_MAPPING = {
    APP_TYPE_HOMGAR: "1",
    APP_TYPE_RAINPOINT: "2",
}

# Brand mappings
BRAND_MAPPING = {
    APP_TYPE_HOMGAR: "HomGar",
    APP_TYPE_RAINPOINT: "RainPoint",
}

