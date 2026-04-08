"""Decoder for HCS999FRF sensor."""
from .legacy import decode_unknown


def decode_hcs999frf(raw: str) -> dict:
    """Decode HCS999FRF (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
