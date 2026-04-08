"""
Decoder functions for HomGar API.

This module is a backward-compatibility shim.
All decoders have been moved to api/decoders/<model>.py — one file per device model.
"""

from .decoders import (
    decode_htv213frf,
    decode_htv0542frf,
    decode_htv113frf,
    decode_valve_hub,
    decode_hws019wrf_v2,
    decode_hcs012arf,
    decode_hcs026frf,
    decode_hcs021frf,
    decode_hcs008frf,
    decode_hcs0530tho,
    decode_pool_plus,
    decode_hcs0528arf,
    decode_hcs0565arf,
    decode_hcs014arf,
    decode_hcs015arf,
    decode_hcs005frf,
    decode_hcs003frf,
    decode_hcs024frf_v1,
    decode_hcs027arf,
    decode_hcs016arf,
    decode_hcs044frf,
    decode_hcs666frf,
    decode_hcs666rfr_p,
    decode_hcs999frf,
    decode_hcs999frf_p,
    decode_hcs666frf_x,
    decode_hcs701b,
    decode_hcs596wb,
    decode_hcs596wb_v4,
    decode_hcs706arf,
    decode_hcs802arf,
    decode_hcs048b,
    decode_hcs888arf_v1,
    decode_hcs0600arf,
    decode_soil,
    decode_temp_hum,
    decode_temp_hum_full,
    decode_display,
    decode_unknown,
)
