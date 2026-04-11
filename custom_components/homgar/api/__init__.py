"""
HomGar API module.

This module provides a clean, organized interface to the HomGar API functionality.
"""

from .client import HomGarClient, HomGarApiError

__all__ = [
    "HomGarClient",
    "HomGarApiError",
]
