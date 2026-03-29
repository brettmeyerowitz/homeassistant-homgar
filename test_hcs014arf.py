#!/usr/bin/env python3

# Test the HCS014ARF flexible decoder with the actual payload
import sys
sys.path.append('/Users/brettmeyerowitz/Code/homeassistant-homgar/custom_components/homgar')

try:
    from homgar_api import decode_hcs014arf
    
    # Test payload from Shaun's error
    test_payload_bytes = [231, 222, 2, 9, 3, 220, 1, 184, 5, 133, 9, 3, 136, 58, 233, 56, 61, 255, 15, 7, 184, 250, 24]
    
    # Convert to hex string format
    hex_str = ''.join(f'{b:02x}' for b in test_payload_bytes)
    raw_payload = f"10#{hex_str}"
    
    print(f"Testing HCS014ARF decoder with payload: {raw_payload}")
    print(f"Payload length: {len(test_payload_bytes)} bytes")
    print()
    
    try:
        result = decode_hcs014arf(raw_payload)
        print("✅ SUCCESS: Flexible decoder worked!")
        print()
        print("Results:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()

except ImportError as e:
    print(f"❌ Import failed: {e}")
    print("Make sure the homgar_api module is available")
