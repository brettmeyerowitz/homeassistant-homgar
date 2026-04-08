"""Decoder for HCS003FRF Moisture sensor (delegates to HCS026FRF)."""
from .hcs026frf import decode_hcs026frf


def decode_hcs003frf(raw: str) -> dict:
    """Decode HCS003FRF (moisture-only sensor)."""
    return decode_hcs026frf(raw)
