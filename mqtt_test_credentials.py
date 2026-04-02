#!/usr/bin/env python3
"""
Generate MQTT credentials for Alibaba Cloud IoT Platform
Based on: https://github.com/martinpeniak/tao-irrigation (working implementation)
"""

import hmac
import hashlib

# From login response
PRODUCT_KEY = "a3iCXW3C5CP"
DEVICE_NAME = "RhTHilOE2Ii86di8ncls"
DEVICE_SECRET = "8aa7906b2fd790b4ecf88131163ad4b1"
MQTT_HOST = "a3iCXW3C5CP.iot-as-mqtt.us-west-1.aliyuncs.com"
MQTT_PORT = 1883

# Client ID format: {deviceName}|securemode=3,signmethod=hmacsha1|
# Note: securemode=3 (TLS disabled), hmacsha1, NO timestamp
client_id = f"{DEVICE_NAME}|securemode=3,signmethod=hmacsha1|"

# Username format: {deviceName}&{productKey}
username = f"{DEVICE_NAME}&{PRODUCT_KEY}"

# Password - HMAC-SHA1 signature (NOT SHA256!)
# Content format: clientId{deviceName}deviceName{deviceName}productKey{productKey}
# Note: NO timestamp in signature content
content = f"clientId{DEVICE_NAME}deviceName{DEVICE_NAME}productKey{PRODUCT_KEY}"
password = hmac.new(
    DEVICE_SECRET.encode('utf-8'),
    content.encode('utf-8'),
    hashlib.sha1  # SHA1, not SHA256!
).hexdigest()

print("=" * 80)
print("MQTT Connection Details - CORRECTED (from tao-irrigation)")
print("=" * 80)
print(f"\nBroker: {MQTT_HOST}")
print(f"Port: {MQTT_PORT}")
print(f"\nClient ID:\n{client_id}")
print(f"\nUsername:\n{username}")
print(f"\nPassword:\n{password}")
print("\n" + "=" * 80)
print("Subscription Topic (from working implementation):")
print("=" * 80)
print(f"/sys/{PRODUCT_KEY}/{DEVICE_NAME}/thing/service/property/set")
print("\n" + "=" * 80)
print("Test with mosquitto_sub:")
print("=" * 80)
print(f"mosquitto_sub -h {MQTT_HOST} -p {MQTT_PORT} \\")
print(f"  -i '{client_id}' \\")
print(f"  -u '{username}' \\")
print(f"  -P '{password}' \\")
print(f"  -t '/sys/{PRODUCT_KEY}/{DEVICE_NAME}/thing/service/property/set' \\")
print("  -d")
print("\n" + "=" * 80)
print("Message Format:")
print("=" * 80)
print('{"params": {"param": "#P{timestamp}{uid}|{hub_mid}|{D01: {...}}|..."}}')
print("\n")
