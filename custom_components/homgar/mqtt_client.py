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

PROP_SET_TOPIC = "/sys/{product_key}/{device_name}/thing/service/property/set"


def _build_aliyun_auth(product_key: str, device_name: str, device_secret: str) -> tuple[str, str, str]:
    """Build Alibaba Cloud IoT MQTT authentication credentials.
    
    Returns: (client_id, username, password)
    """
    client_id = f"{device_name}|securemode=3,signmethod=hmacsha1|"
    content = f"clientId{device_name}deviceName{device_name}productKey{product_key}"
    sign = hmac.new(device_secret.encode(), content.encode(), hashlib.sha1).hexdigest()
    username = f"{device_name}&{product_key}"
    
    _LOGGER.debug(
        "HomGar MQTT auth: client_id=%s username=%s sign=%s",
        client_id,
        username,
        sign[:16] + "...",
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
        
        self._client = None
        self._connected = False
        self._client_lock = threading.Lock()
        self._shutdown_requested = False
        self._reconnect_thread = None
        
        # Build authentication
        self._client_id, self._username, self._password = _build_aliyun_auth(
            product_key, device_name, device_secret
        )
        self._topic = PROP_SET_TOPIC.format(
            product_key=product_key,
            device_name=device_name,
        )
        
        _LOGGER.info(
            "HomGar MQTT client initialized: host=%s port=%d topic=%s",
            mqtt_host,
            mqtt_port,
            self._topic,
        )
    
    def connect(self) -> bool:
        """Connect to MQTT broker."""
        try:
            self._shutdown_requested = False
            self._connect_client()
            return self._wait_for_connection()
        except Exception as e:
            _LOGGER.error("HomGar MQTT connect error: %s", e, exc_info=True)
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker."""
        _LOGGER.info("HomGar MQTT disconnect requested")
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
        """Build MQTT client instance."""
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
            _LOGGER.info("HomGar MQTT connecting to %s:%d", self._mqtt_host, self._mqtt_port)
            self._client.connect(self._mqtt_host, self._mqtt_port, 60)
            self._client.loop_start()
    
    def _wait_for_connection(self) -> bool:
        """Wait for MQTT connection to establish."""
        for i in range(20):
            if self._connected:
                _LOGGER.info("HomGar MQTT connection established after %d attempts", i + 1)
                return True
            time.sleep(0.5)
        _LOGGER.error("HomGar MQTT connection timeout after 10 seconds")
        return False
    
    def _on_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection event."""
        if rc == 0:
            self._connected = True
            client.subscribe(self._topic, qos=0)
            _LOGGER.info("HomGar MQTT connected successfully, subscribed to: %s", self._topic)
        else:
            _LOGGER.error("HomGar MQTT connect failed with rc=%s", rc)
    
    def _on_disconnect(self, client, userdata, rc):
        """Handle MQTT disconnection event."""
        self._connected = False
        if self._shutdown_requested:
            _LOGGER.info("HomGar MQTT disconnected cleanly (shutdown requested)")
            return
        
        _LOGGER.warning("HomGar MQTT disconnected unexpectedly (rc=%s) - will attempt reconnect", rc)
        if rc != 0:
            self._start_reconnect_thread()
    
    def _start_reconnect_thread(self) -> None:
        """Start background reconnection thread."""
        if self._shutdown_requested:
            return
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            _LOGGER.debug("HomGar MQTT reconnect thread already running")
            return
        
        _LOGGER.info("HomGar MQTT starting reconnect thread")
        self._reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self._reconnect_thread.start()
    
    def _reconnect_loop(self):
        """Background reconnection loop."""
        for attempt in range(1, 6):
            if self._shutdown_requested:
                _LOGGER.info("HomGar MQTT reconnect cancelled (shutdown requested)")
                return
            
            delay = min(30 * attempt, 300)
            _LOGGER.info("HomGar MQTT reconnect attempt %d in %d seconds", attempt, delay)
            time.sleep(delay)
            
            try:
                self._connect_client()
                if self._wait_for_connection():
                    _LOGGER.info("HomGar MQTT reconnected successfully on attempt %d", attempt)
                    return
                raise RuntimeError("MQTT reconnect timed out")
            except Exception as e:
                _LOGGER.error("HomGar MQTT reconnect attempt %d failed: %s", attempt, e)
        
        _LOGGER.error("HomGar MQTT reconnect exhausted after 5 attempts")
    
    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT message."""
        try:
            _LOGGER.debug(
                "HomGar MQTT message received: topic=%s payload_len=%d",
                msg.topic,
                len(msg.payload),
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
            
            # Extract hub MID from first part (last 5 digits)
            hub_mid = parts[0][-5:].lstrip("0") or parts[0][-5:]
            rest = parts[1]
            
            # Extract device updates (before final | separators)
            d_updates_raw = rest.rsplit("|", 2)[0] if rest.count("|") >= 2 else rest
            
            try:
                d_updates = json.loads(d_updates_raw)
            except json.JSONDecodeError:
                _LOGGER.warning("HomGar MQTT failed to parse device updates: %s", d_updates_raw[:100])
                return
            
            _LOGGER.info(
                "HomGar MQTT update for hub_mid=%s: %d device(s)",
                hub_mid,
                len(d_updates),
            )
            
            # Process each device update (D01, D02, D03, D04, etc.)
            for key, val in d_updates.items():
                if not key.startswith("D"):
                    continue
                
                raw_val = val.get("value", "") if isinstance(val, dict) else val
                if not raw_val or "#" not in str(raw_val):
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
                    "device_key": key,
                    "payload": str(raw_val),
                })
        
        except Exception as e:
            _LOGGER.error("HomGar MQTT message processing error: %s", e, exc_info=True)
