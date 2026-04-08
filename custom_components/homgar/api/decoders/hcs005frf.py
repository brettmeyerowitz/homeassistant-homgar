"""Decoder for HCS005FRF Moisture sensor (delegates to HCS026FRF)."""
from .hcs026frf import decode_hcs026frf


def decode_hcs005frf(raw: str) -> dict:
    """Decode HCS005FRF (moisture-only sensor)."""
    return decode_hcs026frf(raw)
