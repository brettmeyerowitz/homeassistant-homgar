"""Decoder for HCS666FRF sensor."""
from .legacy import decode_unknown


def decode_hcs666frf(raw: str) -> dict:
    """Decode HCS666FRF (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
