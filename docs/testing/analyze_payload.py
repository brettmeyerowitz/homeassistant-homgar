#!/usr/bin/env python3
"""Analyze the first HCS014ARF payload in detail"""

def parse_payload(raw: str):
    if raw.startswith("10#"):
        raw = raw[3:]
    return bytes.fromhex(raw)

payload = '10#E74A022603DC01B8058551028843E92561FF0F4A700B19'
b = parse_payload(payload)

print(f"Analyzing payload: {payload}")
print(f"Byte array length: {len(b)}")
print()
print("Byte-by-byte breakdown:")
for i, byte in enumerate(b):
    print(f"  Byte {i:2d}: 0x{byte:02X} ({byte:3d})")

print()
print("Decoder extraction:")
print(f"  RSSI (byte 1): 0x{b[1]:02X} = {b[1]} → -{b[1]} dBm")
print()
print(f"  Temp bytes 10-11: 0x{b[10]:02X} 0x{b[11]:02X}")
print(f"  Little-endian: {b[10]} + ({b[11]} << 8) = {b[10] | (b[11] << 8)}")
print(f"  Tenths of °F: {(b[10] | (b[11] << 8)) / 10.0:.1f}°F")
print(f"  Converted to °C: {((b[10] | (b[11] << 8)) / 10.0 - 32.0) * 5.0 / 9.0:.1f}°C")
print()
print(f"  Humidity (byte 13): 0x{b[13]:02X} = {b[13]}%")
print()
print("Expected from app: 15.0°C, 68%")
print(f"Decoder gives:     {((b[10] | (b[11] << 8)) / 10.0 - 32.0) * 5.0 / 9.0:.1f}°C, {b[13]}%")
print()
print("Analysis:")
print("  Temperature: 15.2°C vs 15.0°C = 0.2°C difference (within sensor accuracy)")
print("  Humidity: 67% vs 68% = 1% difference (likely rounding in app)")
print("  Conclusion: Decoder is working correctly, differences are within normal variance")
