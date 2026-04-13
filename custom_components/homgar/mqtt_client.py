"""MQTT client for real-time HomGar/RainPoint valve state updates.

Based on: https://github.com/martinpeniak/tao-irrigation
"""
import asyncio
import hashlib
import hmac
import json
import logging
import threading
import time
from typing import Callable

try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)

TOPICS_TEMPLATE = [
    "/sys/{product_key}/{device_name}/thing/event/property/post",
    "/sys/{product_key}/{device_name}/thing/service/property/set",
    "/sys/{product_key}/{device_name}/thing/status/update",
    "/sys/{product_key}/{device_name}/thing/sub/event/property/post",
    "/sys/{product_key}/{device_name}/thing/sub/status/update",
]


def _extract_device_updates(rest: str) -> dict | None:
    """Extract the JSON device-update object from an MQTT param tail.

    Some observed messages include scalar segments such as hub IDs or counters
    between pipe delimiters before the actual JSON object. We only want the
    object containing Dxx updates.
    """
    start = rest.find("{")
    end = rest.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    try:
        parsed = json.loads(rest[start:end + 1])
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def _extract_hub_mid_candidates(prefix_full: str) -> tuple[str, list[str]]:
    """Extract possible hub MID values from the MQTT prefix."""
    last6 = prefix_full[-6:]
    raw_mid = last6.lstrip("0") or "0"
    candidates: list[str] = []

    def add(candidate: str) -> None:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    add(raw_mid)
    if len(raw_mid) == 6 and raw_mid.endswith("0"):
        add(raw_mid[:-1])
    if len(raw_mid) == 6 and raw_mid.startswith("1"):
        add(raw_mid[1:])

    return last6, candidates


def _looks_like_device_payload(raw_val: str) -> bool:
    """Return True when an MQTT device value looks like a real device payload.

    We accept both TLV/hex payloads (e.g. ``10#...``) and the older ASCII
    payloads used by some RainPoint valve timers (e.g. ``1,-71,1;...|...``).
    """
    raw = str(raw_val).strip()
    if not raw:
        return False

    if "#" in raw:
        return True

    return ";" in raw and "," in raw


def _build_aliyun_auth(product_key: str, device_name: str, device_secret: str) -> tuple[str, str, str]:
    """Build Alibaba Cloud IoT MQTT authentication credentials (securemode=2, Observer mode).
    
    Returns: (client_id, username, password)
    """
    timestamp_ms = str(int(time.time() * 1000))
    client_id = f"{device_name}|securemode=2,signmethod=hmacsha1,timestamp={timestamp_ms}|"
    content = f"clientId{device_name}deviceName{device_name}productKey{product_key}timestamp{timestamp_ms}"
    sign = hmac.new(device_secret.encode(), content.encode(), hashlib.sha1).hexdigest()
    username = f"{device_name}&{product_key}"
    
    _LOGGER.debug(
        "HomGar MQTT auth: client_id=<redacted> username=%s",
        username.split("&")[0][:8] + "...",  # device name prefix only, no product key
    )
    
    return client_id, username, sign


class HomGarMQTTClient:
    """MQTT client for HomGar/RainPoint real-time updates."""
    
    def __init__(
        self,
        product_key: str,
        device_name: str,
        device_secret: str,
        mqtt_host: str,
        on_message_callback: Callable[[dict], None],
        mqtt_port: int = 1883,
        entry_title: str = "",
    ):
        """Initialize MQTT client."""
        if not PAHO_AVAILABLE:
            raise RuntimeError("paho-mqtt required: pip install paho-mqtt>=1.6.0")
        
        self._product_key = product_key
        self._device_name = device_name
        self._device_secret = device_secret
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._on_message_callback = on_message_callback
        self._entry_title = entry_title
        
        self._client = None
        self._connected = False
        self._client_lock = threading.Lock()
        self._shutdown_requested = False
        self._reconnect_thread = None
        
        # MQTT diagnostics
        self._messages_received = 0
        self._messages_sent = 0
        self._connection_attempts = 0
        self._last_connect_time = None
        self._last_message_time = None
        
        # Build authentication
        self._client_id, self._username, self._password = _build_aliyun_auth(
            product_key, device_name, device_secret
        )
        self._topics = [
            t.format(product_key=product_key, device_name=device_name)
            for t in TOPICS_TEMPLATE
        ]
        
        label = f" [{entry_title}]" if entry_title else ""
        _LOGGER.info(
            "HomGar MQTT%s client initialized: host=%s port=%d topics=%d",
            label,
            mqtt_host,
            mqtt_port,
            len(self._topics),
        )
    
    def _label(self) -> str:
        return f" [{self._entry_title}]" if self._entry_title else ""

    def connect(self) -> bool:
        """Connect to MQTT broker."""
        try:
            self._shutdown_requested = False
            self._connection_attempts += 1
            self._connect_client()
            return self._wait_for_connection()
        except Exception as e:
            _LOGGER.error("HomGar MQTT%s connect error: %s", self._label(), e, exc_info=True)
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker."""
        _LOGGER.info("HomGar MQTT%s disconnect requested", self._label())
        self._shutdown_requested = True
        with self._client_lock:
            if self._client:
                try:
                    self._client.loop_stop()
                except Exception:
                    _LOGGER.debug("HomGar MQTT loop_stop failed during disconnect", exc_info=True)
                try:
                    self._client.disconnect()
                except Exception:
                    _LOGGER.debug("HomGar MQTT disconnect failed during shutdown", exc_info=True)
    
    def _build_client(self):
        """Build MQTT client instance with fresh timestamp credentials."""
        # Regenerate auth on every connect — securemode=2 timestamp must be fresh
        self._client_id, self._username, self._password = _build_aliyun_auth(
            self._product_key, self._device_name, self._device_secret
        )
        client = mqtt.Client(client_id=self._client_id, protocol=mqtt.MQTTv311)
        client.username_pw_set(self._username, self._password)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        return client
    
    def _connect_client(self) -> None:
        """Connect MQTT client to broker."""
        self._connected = False
        with self._client_lock:
            if self._client:
                try:
                    self._client.loop_stop()
                except Exception:
                    _LOGGER.debug("HomGar MQTT loop_stop failed before reconnect", exc_info=True)
                try:
                    self._client.disconnect()
                except Exception:
                    _LOGGER.debug("HomGar MQTT disconnect failed before reconnect", exc_info=True)
            
            self._client = self._build_client()
            _LOGGER.info("HomGar MQTT%s connecting to %s:%d", self._label(), self._mqtt_host, self._mqtt_port)
            self._client.connect(self._mqtt_host, self._mqtt_port, 60)
            self._client.loop_start()
    
    def _wait_for_connection(self) -> bool:
        """Wait for MQTT connection to establish."""
        for i in range(20):
            if self._connected:
                _LOGGER.info(
                    "HomGar MQTT%s connection established after %d attempts", self._label(), i + 1)
                return True
            time.sleep(0.5)
        _LOGGER.error("HomGar MQTT%s connection timeout after 10 seconds", self._label())
        return False
    
    def _on_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection event."""
        if rc == 0:
            self._connected = True
            self._last_connect_time = time.time()
            for topic in self._topics:
                client.subscribe(topic, qos=0)
            _LOGGER.info("HomGar MQTT%s connected successfully, subscribed to %d topics", self._label(), len(self._topics))
        else:
            _LOGGER.error("HomGar MQTT%s connect failed with rc=%s", self._label(), rc)
    
    def _on_disconnect(self, client, userdata, rc):
        """Handle MQTT disconnection event."""
        self._connected = False
        if self._shutdown_requested:
            _LOGGER.info("HomGar MQTT%s disconnected cleanly (shutdown requested)", self._label())
            return
        
        _LOGGER.warning("HomGar MQTT%s disconnected unexpectedly (rc=%s) - will attempt reconnect", self._label(), rc)
        if rc != 0:
            self._start_reconnect_thread()
    
    def _start_reconnect_thread(self) -> None:
        """Start background reconnection thread."""
        if self._shutdown_requested:
            return
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            _LOGGER.debug("HomGar MQTT reconnect thread already running")
            return
        
        _LOGGER.info("HomGar MQTT%s starting reconnect thread", self._label())
        self._reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self._reconnect_thread.start()
    
    def _reconnect_loop(self):
        """Background reconnection loop."""
        for attempt in range(1, 6):
            if self._shutdown_requested:
                _LOGGER.info("HomGar MQTT reconnect cancelled (shutdown requested)")
                return
            
            delay = min(30 * attempt, 300)
            _LOGGER.info("HomGar MQTT%s reconnect attempt %d in %d seconds", self._label(), attempt, delay)
            time.sleep(delay)
            
            try:
                self._connect_client()
                if self._wait_for_connection():
                    _LOGGER.info("HomGar MQTT%s reconnected successfully on attempt %d", self._label(), attempt)
                    return
                raise RuntimeError("MQTT reconnect timed out")
            except Exception as e:
                _LOGGER.error("HomGar MQTT%s reconnect attempt %d failed: %s", self._label(), attempt, e)
        
        _LOGGER.error("HomGar MQTT%s reconnect exhausted after 5 attempts", self._label())
    
    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT message."""
        try:
            self._messages_received += 1
            self._last_message_time = time.time()
            
            _LOGGER.debug(
                "HomGar MQTT message received: topic=%s payload_len=%d total=%d",
                msg.topic,
                len(msg.payload),
                self._messages_received,
            )
            
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
            _LOGGER.debug("HomGar MQTT parsed payload: %s", payload)
            
            param_str = payload.get("params", {}).get("param", "")
            if not param_str or not param_str.startswith("#P"):
                _LOGGER.debug("HomGar MQTT message missing #P prefix, ignoring")
                return
            
            # Parse message format: #P{timestamp}{uid}|{hub_mid}|{D01: {...}, D02: {...}}|...
            inner = param_str.strip("#")
            parts = inner.split("|", 1)
            if len(parts) < 2:
                _LOGGER.warning("HomGar MQTT message invalid format: %s", param_str[:100])
                return
            
            prefix_full = parts[0]
            last6, hub_mid_candidates = _extract_hub_mid_candidates(prefix_full)
            hub_mid = hub_mid_candidates[0]
            
            _LOGGER.debug(
                "HomGar MQTT hub MID extraction: prefix_last6=%s candidates=%s selected=%s",
                last6,
                hub_mid_candidates,
                hub_mid,
            )
            rest = parts[1]
            
            d_updates = _extract_device_updates(rest)
            if d_updates is None:
                if "{" not in rest:
                    _LOGGER.debug("HomGar MQTT ignoring non-device update fragment: %s", rest[:100])
                else:
                    _LOGGER.warning("HomGar MQTT failed to parse device updates: %s", rest[:100])
                return
            
            device_count = sum(1 for key in d_updates if isinstance(key, str) and key.startswith("D"))
            _LOGGER.debug(
                "HomGar MQTT update for hub_mid=%s: %d device(s)",
                hub_mid,
                device_count,
            )
            
            # Process each device update (D01, D02, D03, D04, etc.)
            for key, val in d_updates.items():
                if not key.startswith("D"):
                    continue
                
                raw_val = val.get("value", "") if isinstance(val, dict) else val
                if not _looks_like_device_payload(str(raw_val)):
                    continue
                
                _LOGGER.debug(
                    "HomGar MQTT device update: hub_mid=%s key=%s value=%s",
                    hub_mid,
                    key,
                    str(raw_val)[:100],
                )
                
                # Call callback with parsed data
                self._on_message_callback({
                    "hub_mid": hub_mid,
                    "hub_mid_candidates": hub_mid_candidates,
                    "device_key": key,
                    "payload": str(raw_val),
                })
        
        except Exception as e:
            _LOGGER.error("HomGar MQTT message processing error: %s", e, exc_info=True)

    def get_diagnostics(self) -> dict:
        """Get MQTT diagnostic information."""
        uptime = time.time() - (self._last_connect_time or time.time())
        last_message_age = time.time() - (self._last_message_time or time.time())
        
        return {
            "connected": self._connected,
            "connection_attempts": self._connection_attempts,
            "messages_received": self._messages_received,
            "messages_sent": self._messages_sent,
            "last_connect_time": self._last_connect_time,
            "last_message_time": self._last_message_time,
            "uptime_seconds": max(0, uptime),
            "last_message_age_seconds": last_message_age if self._last_message_time else None,
            "mqtt_host": self._mqtt_host,
            "mqtt_port": self._mqtt_port,
            "topics": self._topics,
        }

    def send_message(self, payload: dict) -> bool:
        """Send MQTT message and track diagnostics."""
        if not self._connected or not self._client:
            _LOGGER.warning("HomGar MQTT not connected, cannot send message")
            return False
        
        try:
            message = json.dumps(payload)
            prop_set_topic = next((t for t in self._topics if "property/set" in t), self._topics[0])
            result = self._client.publish(prop_set_topic, message, qos=0)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self._messages_sent += 1
                _LOGGER.debug("HomGar MQTT message sent successfully (total: %d)", self._messages_sent)
                return True
            else:
                _LOGGER.error("HomGar MQTT send failed with rc=%s", result.rc)
                return False
        except Exception as e:
            _LOGGER.error("HomGar MQTT send error: %s", e, exc_info=True)
            return False
