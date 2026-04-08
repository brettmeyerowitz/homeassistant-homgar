"""Decoder for HCS999FRF-P sensor."""
from .legacy import decode_unknown


def decode_hcs999frf_p(raw: str) -> dict:
    """Decode HCS999FRF-P (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
