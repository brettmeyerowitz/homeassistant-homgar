"""Decoder for HCS0600ARF advanced environmental sensor."""
from .legacy import decode_unknown


def decode_hcs0600arf(raw: str) -> dict:
    """Decode HCS0600ARF (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
