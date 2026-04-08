"""Decoder for HCS016ARF Temperature/Humidity sensor."""
from .legacy import decode_unknown


def decode_hcs016arf(raw: str) -> dict:
    """Decode HCS016ARF (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
