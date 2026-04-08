"""Decoder for HCS596WB weather station base sensor."""
from .legacy import decode_unknown


def decode_hcs596wb(raw: str) -> dict:
    """Decode HCS596WB (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
