"""HomGar API - thin shim re-exporting HomGarClient from the api/ subpackage."""

from .api import HomGarClient
from .api.client import HomGarApiError

__all__ = [
    'HomGarClient',
    'HomGarApiError',
]
