"""Decoder for HCS666RFR-P sensor."""
from .legacy import decode_unknown


def decode_hcs666rfr_p(raw: str) -> dict:
    """Decode HCS666RFR-P (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
