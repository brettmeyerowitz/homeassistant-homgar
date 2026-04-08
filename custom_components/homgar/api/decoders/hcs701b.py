"""Decoder for HCS701B wall-mounted Temperature/Humidity sensor."""
from .legacy import decode_unknown


def decode_hcs701b(raw: str) -> dict:
    """Decode HCS701B (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
