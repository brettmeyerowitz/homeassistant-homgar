"""Decoder for HCS706ARF environmental sensor."""
from .legacy import decode_unknown


def decode_hcs706arf(raw: str) -> dict:
    """Decode HCS706ARF (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
