#!/usr/bin/env python3
"""Test HCS014ARF decoder logic directly"""

def parse_payload(raw: str):
    """Parse hex payload"""
    if raw.startswith("10#"):
        raw = raw[3:]
    return bytes.fromhex(raw)

def test_hcs014arf():
    """Test HCS014ARF decoder with known values from Issue #21"""
    
    test_cases = [
        ('10#E74A022603DC01B8058551028843E92561FF0F4A700B19', 15.0, 68),
        ('10#E74A022603DC01B805854E028844E92561FF0F98710B19', 15.0, 68),
        ('10#E74A022603DC01B8058558028845E92561FF0FD4760B19', 15.6, 69),
        ('10#E74A022603DC01B805855E028843E92561FF0F197A0B19', 15.9, 67),
        ('10#E74A022603DC01B8058560028843E92561FF0F0F7C0B19', 16.0, 67),
    ]
    
    print('Testing HCS014ARF decoder with Issue #21 payloads:')
    print('=' * 80)
    
    all_passed = True
    for payload, expected_temp, expected_hum in test_cases:
        b = parse_payload(payload)
        
        # Extract RSSI from byte 1
        rssi_raw = b[1]
        rssi_dbm = -rssi_raw if rssi_raw > 0 else 0
        
        # Extract temperature from bytes 10-11 (little-endian, tenths of °F)
        temp_raw_f10 = b[10] | (b[11] << 8)
        temp_f = temp_raw_f10 / 10.0
        temp_c = (temp_f - 32.0) * 5.0 / 9.0
        
        # Extract humidity from byte 13
        humidity = b[13]
        
        temp_match = abs(temp_c - expected_temp) < 0.2
        hum_match = humidity == expected_hum
        
        passed = temp_match and hum_match
        all_passed = all_passed and passed
        
        status = '✓' if passed else '✗'
        print(f'{status} Payload: {payload[:40]}...')
        print(f'  Expected: {expected_temp}°C, {expected_hum}%')
        print(f'  Got:      {temp_c:.1f}°C, {humidity}%')
        print(f'  RSSI:     {rssi_dbm} dBm')
        print(f'  Raw temp: {temp_raw_f10} (tenths of °F) = {temp_f:.1f}°F')
        if not passed:
            print(f'  *** MISMATCH! ***')
        print()
    
    print('=' * 80)
    if all_passed:
        print('✓ All tests PASSED - Decoder is correct!')
    else:
        print('✗ Some tests FAILED - Decoder needs fixing')
    
    return all_passed

if __name__ == '__main__':
    import sys
    sys.exit(0 if test_hcs014arf() else 1)
