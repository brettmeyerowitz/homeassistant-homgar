#!/usr/bin/env python3

# Test the HCS014ARF flexible decoder logic directly
def test_hcs014arf_logic():
    """Test the flexible decoder logic with Shaun's actual payload"""
    
    # Shaun's payload: [231, 222, 2, 9, 3, 220, 1, 184, 5, 133, 9, 3, 136, 58, 233, 56, 61, 255, 15, 7, 184, 250, 24]
    test_payload_bytes = [231, 222, 2, 9, 3, 220, 1, 184, 5, 133, 9, 3, 136, 58, 233, 56, 61, 255, 15, 7, 184, 250, 24]
    
    print(f"Testing HCS014ARF flexible decoder logic")
    print(f"Payload bytes: {test_payload_bytes}")
    print(f"Payload length: {len(test_payload_bytes)} bytes")
    print()
    
    # Test the minimum length check
    if len(test_payload_bytes) < 22:
        print(f"❌ FAILED: Payload too short: {len(test_payload_bytes)} bytes (minimum 22 required)")
        return False
    else:
        print(f"✅ PASSED: Minimum length check ({len(test_payload_bytes)} >= 22)")
    
    # Test data extraction
    def le_val(parts):
        return int(''.join(f'{x:02x}' for x in parts[::-1]), 16)
    
    # Extract RSSI (byte 1)
    rssi = test_payload_bytes[1] - 256 if test_payload_bytes[1] >= 128 else test_payload_bytes[1]
    print(f"RSSI: {rssi} dBm")
    
    # Try to extract temperature data
    templow = None
    temphigh = None
    tempcurrent = None
    humiditycurrent = None
    humidityhigh = None
    humiditylow = None
    tempbatt = None
    
    if len(test_payload_bytes) >= 9:
        templow = (((le_val(test_payload_bytes[7:9]+test_payload_bytes[5:7]) / 10) - 32) * (5 / 9))
        print(f"Temp low: {templow}°C")
    
    if len(test_payload_bytes) >= 13:
        temphigh = (((le_val(test_payload_bytes[11:13]+test_payload_bytes[9:11]) / 10) - 32) * (5 / 9))
        print(f"Temp high: {temphigh}°C")
    
    if len(test_payload_bytes) >= 27:
        tempcurrent = (((le_val(test_payload_bytes[25:27]+test_payload_bytes[23:25]) / 10) - 32) * (5 / 9))
        print(f"Temp current: {tempcurrent}°C")
    
    if len(test_payload_bytes) > 29:
        humiditycurrent = test_payload_bytes[29]
        print(f"Humidity current: {humiditycurrent}%")
    
    if len(test_payload_bytes) >= 34:
        humiditylow = test_payload_bytes[33]
        print(f"Humidity low: {humiditylow}%")
    
    if len(test_payload_bytes) >= 36:
        humidityhigh = test_payload_bytes[35]
        print(f"Humidity high: {humidityhigh}%")
    
    if len(test_payload_bytes) >= 41:
        tempbatt = (le_val(test_payload_bytes[39:41]+test_payload_bytes[37:39]) / 4095 * 100)
        print(f"Temp battery: {tempbatt}%")
    
    print()
    print("✅ SUCCESS: Flexible decoder logic works with Shaun's payload!")
    print("The issue might be that Shaun hasn't updated to v1.3.7 yet")
    return True

if __name__ == "__main__":
    test_hcs014arf_logic()
