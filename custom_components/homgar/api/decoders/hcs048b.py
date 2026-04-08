"""Decoder for HCS048B compact sensor."""
from .legacy import decode_unknown


def decode_hcs048b(raw: str) -> dict:
    """Decode HCS048B (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
