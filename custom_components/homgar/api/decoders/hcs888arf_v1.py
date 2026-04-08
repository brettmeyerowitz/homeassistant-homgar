"""Decoder for HCS888ARF-V1 multi-function sensor."""
from .legacy import decode_unknown


def decode_hcs888arf_v1(raw: str) -> dict:
    """Decode HCS888ARF-V1 (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
