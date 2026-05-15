DOMAIN = "homgar"
NAME = "HomGar/RainPoint Cloud"

CONF_AREA_CODE = "area_code"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_HIDS = "hids"  # list of selected home IDs
CONF_APP_TYPE = "app_type"  # "homgar" or "rainpoint"
CONF_GROUP_MULTI_ZONE_DEVICES = "group_multi_zone_devices"
CONF_VALVE_DURATION_UNIT = "valve_duration_unit"

VALVE_DURATION_UNIT_MINUTES = "minutes"
VALVE_DURATION_UNIT_SECONDS = "seconds"
DEFAULT_VALVE_DURATION_UNIT = VALVE_DURATION_UNIT_MINUTES

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
    *,
    use_device_prefix: bool = False,
) -> str:
    """Format a user-facing per-port entity name without changing unique IDs."""
    if use_device_prefix:
        parts = [format_port_device_name(sub_name, sensor_info, port)]
    else:
        port_label = get_port_label(sensor_info, port) or f"Zone {port}"
        parts = [sub_name, port_label]
    if suffix:
        parts.append(suffix)
    return " ".join(parts)


def format_port_device_name(
    sub_name: str,
    sensor_info: dict,
    port: int,
) -> str:
    """Format the HA device name for a single controller port."""
    port_label = get_port_label(sensor_info, port) or f"Zone {port}"
    return f"{sub_name} - {port_label}"


def zone_device_identifier(mid: int | str, addr: int | str, port: int) -> str:
    """Return the stable HA device identifier for a controller port."""
    return f"{mid}_{addr}_zone{port}"


def controller_device_identifier(sensor_info: dict) -> str:
    """Return the HA device identifier for the parent controller device."""
    mid = sensor_info["mid"]
    if sensor_info.get("type_flag") == 1:
        return f"rainpoint_hub_{mid}"
    addr = sensor_info["addr"]
    return f"{mid}_{addr}"
