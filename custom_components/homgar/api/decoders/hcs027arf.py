"""Decoder for HCS027ARF Temperature/Humidity sensor."""
from .legacy import decode_unknown


def decode_hcs027arf(raw: str) -> dict:
    """Decode HCS027ARF (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
