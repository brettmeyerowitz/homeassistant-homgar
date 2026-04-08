"""Decoder for HCS024FRF-V1 Multi-sensor (delegates to HCS021FRF)."""
from .hcs021frf import decode_hcs021frf


def decode_hcs024frf_v1(raw: str) -> dict:
    """Decode HCS024FRF-V1 (multi-sensor: temp + moisture + lux)."""
    return decode_hcs021frf(raw)
