DOMAIN = "homgar"
NAME = "HomGar/RainPoint Cloud"

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


def get_port_labels(sensor_info: dict) -> list[str]:
    """Return per-port friendly labels parsed from a sub-device portDescribe."""
    raw = sensor_info.get("port_describe") or ""
    if not isinstance(raw, str):
        return []
    return [part.strip() for part in raw.split("|") if part.strip()]


def get_port_label(sensor_info: dict, port: int) -> str | None:
    """Return the configured friendly label for a 1-based port, if present."""
    labels = get_port_labels(sensor_info)
    if 1 <= port <= len(labels):
        return labels[port - 1]
    return None


def format_port_entity_name(
    sub_name: str,
    sensor_info: dict,
    port: int,
    suffix: str | None = None,
) -> str:
    """Format a user-facing per-port entity name without changing unique IDs."""
    port_label = get_port_label(sensor_info, port) or f"Zone {port}"
    parts = [sub_name, port_label]
    if suffix:
        parts.append(suffix)
    return " ".join(parts)
