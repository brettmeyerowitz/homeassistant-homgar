"""Decoder for HCS666FRF-X sensor."""
from .legacy import decode_unknown


def decode_hcs666frf_x(raw: str) -> dict:
    """Decode HCS666FRF-X (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
