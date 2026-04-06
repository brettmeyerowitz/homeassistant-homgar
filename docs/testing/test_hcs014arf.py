#!/usr/bin/env python3
"""Test HCS014ARF decoder with known payloads from Issue #21"""

import sys
sys.path.insert(0, 'custom_components/homgar')

from api.decoders import decode_temphum

# Test payloads from Issue #21 with known values from app
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
    result = decode_temphum(payload)
    temp_c = result.get('temperature_c', 0)
    humidity = result.get('humidity_percent', 0)
    
    temp_match = abs(temp_c - expected_temp) < 0.2
    hum_match = humidity == expected_hum
    
    passed = temp_match and hum_match
    all_passed = all_passed and passed
    
    status = '✓' if passed else '✗'
    print(f'{status} Payload: {payload[:40]}...')
    print(f'  Expected: {expected_temp}°C, {expected_hum}%')
    print(f'  Got:      {temp_c:.1f}°C, {humidity}%')
    if not passed:
        print(f'  MISMATCH!')
    print()

print('=' * 80)
if all_passed:
    print('✓ All tests PASSED')
else:
    print('✗ Some tests FAILED')
