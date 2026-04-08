"""Decoder for HCS802ARF environmental sensor."""
from .legacy import decode_unknown


def decode_hcs802arf(raw: str) -> dict:
    """Decode HCS802ARF (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
