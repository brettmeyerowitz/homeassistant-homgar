"""
Decoder functions for HomGar/RainPoint devices.

One file per device model for easy maintenance.
"""

from .htv213frf import decode_htv213frf
from .htv0542frf import decode_htv0542frf
from .htv113frf import decode_htv113frf
from .valve_hub import decode_valve_hub
from .hws019wrf_v2 import decode_hws019wrf_v2
from .hcs012arf import decode_hcs012arf
from .hcs026frf import decode_hcs026frf
from .hcs021frf import decode_hcs021frf
from .hcs008frf import decode_hcs008frf
from .hcs0530tho import decode_hcs0530tho, decode_pool_plus
from .hcs0528arf import decode_hcs0528arf
from .hcs0565arf import decode_hcs0565arf
from .hcs014arf import decode_hcs014arf
from .hcs015arf import decode_hcs015arf
from .hcs005frf import decode_hcs005frf
from .hcs003frf import decode_hcs003frf
from .hcs024frf_v1 import decode_hcs024frf_v1
from .hcs027arf import decode_hcs027arf
from .hcs016arf import decode_hcs016arf
from .hcs044frf import decode_hcs044frf
from .hcs666frf import decode_hcs666frf
from .hcs666rfr_p import decode_hcs666rfr_p
from .hcs999frf import decode_hcs999frf
from .hcs999frf_p import decode_hcs999frf_p
from .hcs666frf_x import decode_hcs666frf_x
from .hcs701b import decode_hcs701b
from .hcs596wb import decode_hcs596wb
from .hcs596wb_v4 import decode_hcs596wb_v4
from .hcs706arf import decode_hcs706arf
from .hcs802arf import decode_hcs802arf
from .hcs048b import decode_hcs048b
from .hcs888arf_v1 import decode_hcs888arf_v1
from .hcs0600arf import decode_hcs0600arf
from .legacy import decode_soil, decode_temp_hum, decode_temp_hum_full, decode_display, decode_unknown

__all__ = [
    "decode_htv213frf",
    "decode_htv0542frf",
    "decode_htv113frf",
    "decode_valve_hub",
    "decode_hws019wrf_v2",
    "decode_hcs012arf",
    "decode_hcs026frf",
    "decode_hcs021frf",
    "decode_hcs008frf",
    "decode_hcs0530tho",
    "decode_pool_plus",
    "decode_hcs0528arf",
    "decode_hcs0565arf",
    "decode_hcs014arf",
    "decode_hcs015arf",
    "decode_hcs005frf",
    "decode_hcs003frf",
    "decode_hcs024frf_v1",
    "decode_hcs027arf",
    "decode_hcs016arf",
    "decode_hcs044frf",
    "decode_hcs666frf",
    "decode_hcs666rfr_p",
    "decode_hcs999frf",
    "decode_hcs999frf_p",
    "decode_hcs666frf_x",
    "decode_hcs701b",
    "decode_hcs596wb",
    "decode_hcs596wb_v4",
    "decode_hcs706arf",
    "decode_hcs802arf",
    "decode_hcs048b",
    "decode_hcs888arf_v1",
    "decode_hcs0600arf",
    "decode_soil",
    "decode_temp_hum",
    "decode_temp_hum_full",
    "decode_display",
    "decode_unknown",
]
