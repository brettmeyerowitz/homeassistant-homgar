"""Decoder for HCS015ARF Pool Temperature sensor (delegates to HCS0528ARF)."""
from .hcs0528arf import decode_hcs0528arf


def decode_hcs015arf(raw: str) -> dict:
    """Decode HCS015ARF (pool temperature sensor)."""
    return decode_hcs0528arf(raw)
