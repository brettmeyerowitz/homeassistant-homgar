#!/usr/bin/env python3
"""Analyze HIC801W payload from Issue #20"""

def parse_payload(raw: str):
    if raw.startswith("10#"):
        raw = raw[3:]
    return bytes.fromhex(raw)

payload = '10#108800AF00000000B700204200D800F700000000F9FF00'
b = parse_payload(payload)

print(f"Analyzing HIC801W payload: {payload}")
print(f"Byte array length: {len(b)}")
print()
print("Byte-by-byte breakdown:")
for i, byte in enumerate(b):
    print(f"  Byte {i:2d}: 0x{byte:02X} ({byte:3d})")

print()
print("Pattern analysis:")
print("  Byte 0: 0x10 (16) - Could be header/type")
print("  Byte 1: 0x88 (136) - RSSI? -136 dBm seems too low")
print("  Byte 2-3: 0x00 0xAF (0, 175)")
print("  Byte 4-7: 0x00 0x00 0x00 0x00 - Zeros")
print("  Byte 8: 0xB7 (183)")
print("  Byte 9-10: 0x00 0x20 (0, 32)")
print("  Byte 11: 0x42 (66)")
print("  Byte 12-13: 0x00 0xD8 (0, 216)")
print("  Byte 14-15: 0x00 0xF7 (0, 247)")
print("  Byte 16-19: 0x00 0x00 0x00 0x00 - Zeros")
print("  Byte 20-21: 0xF9 0xFF (249, 255)")
print("  Byte 22: 0x00")
print()
print("Observations:")
print("  - Lots of zero bytes (unusual for sensor data)")
print("  - No obvious temperature/humidity pattern")
print("  - Could be a different device type (not environmental sensor)")
print("  - Might be a water sensor, leak detector, or other binary device")
print()
print("Recommendation:")
print("  - Need more payloads to identify pattern")
print("  - Need to know what type of device HIC801W is")
print("  - User should provide device description and multiple payload samples")
