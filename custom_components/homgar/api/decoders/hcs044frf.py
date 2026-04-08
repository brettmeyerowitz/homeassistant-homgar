"""Decoder for HCS044FRF Multi-sensor."""
from .legacy import decode_unknown


def decode_hcs044frf(raw: str) -> dict:
    """Decode HCS044FRF (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
