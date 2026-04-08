"""Decoder for HCS596WB-V4 weather station base sensor."""
from .legacy import decode_unknown


def decode_hcs596wb_v4(raw: str) -> dict:
    """Decode HCS596WB-V4 (payload format not yet reverse-engineered)."""
    return decode_unknown(raw)
