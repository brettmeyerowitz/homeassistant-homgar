"""Product photographs for devices, sourced from the shipped catalogue.

The catalogue's ``productImage`` codes are asset TYPES, not sizes:

    REAL     a colour product photograph  (144x144, on 106 of 107 models)
    BIG      a generic grey category icon (a tap symbol, not the device)
    SMALL    a grey line drawing of the device outline
    EXAMPLE  an in-situ marketing shot

Sizes do not track the names — HCS021FRF's "SMALL" is 371px while its "BIG"
is 216px — so picking by name to get a bigger image does not work.

Only REAL is used, and deliberately without a fallback to the others: putting a
generic tap icon where a device photo belongs is worse than showing no picture,
because Home Assistant's own icon is a better generic than the vendor's.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .decoder import get_model_info

_LOGGER = logging.getLogger(__name__)

#: The only variant that is an actual photograph of the device.
IMAGE_CODE = "REAL"


def image_url_for_model(model: str) -> str | None:
    """Return the product photo URL for ``model``, or None if there isn't one.

    Missing images are a normal case, not an error: one shipped model has no
    ``productImage`` at all, and models newer than the shipped catalogue will
    not be found either.
    """
    if not model:
        return None
    info = get_model_info(model)
    if not info:
        return None
    for entry in info.get("productImage") or []:
        if entry.get("code") == IMAGE_CODE and entry.get("path"):
            return entry["path"]
    return None


#: Where per-instance cache bookkeeping lives. Keeping it on hass.data rather
#: than in a module global means a reload starts clean and there is no
#: test-only reset hook in production code.
_CACHE_KEY = "homgar_product_images"

#: Subdirectory of the HA config dir holding the downloaded photos.
_CACHE_DIR = "homgar_images"


def _state(hass) -> dict:
    return hass.data.setdefault(_CACHE_KEY, {})


def cache_path(hass, model: str) -> str:
    """Absolute path of the cached photo for ``model`` (may not exist yet)."""
    return hass.config.path(_CACHE_DIR, f"{model.upper()}.png")


def _write(path: str, body: bytes) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(body)
    return str(p)


async def async_ensure_cached(hass, session, model: str) -> str | None:
    """Return the local path of ``model``'s photo, fetching it once if needed.

    Returns None when the model has no photo, or when fetching it failed. A
    failure is remembered for the life of the entry: a blocked or dead CDN
    must not be retried on every reload, and a missing photo is a normal
    condition rather than an error worth surfacing to the user.
    """
    state = _state(hass)
    if model in state:
        return state[model]

    url = image_url_for_model(model)
    if not url:
        state[model] = None
        return None

    path = cache_path(hass, model)
    if await hass.async_add_executor_job(Path(path).exists):
        state[model] = path
        return path

    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                _LOGGER.debug("No product image for %s: HTTP %s", model, resp.status)
                state[model] = None
                return None
            body = await resp.read()
    except Exception as exc:  # noqa: BLE001 - a missing picture must never break setup
        _LOGGER.debug("Could not fetch product image for %s: %s", model, exc)
        state[model] = None
        return None

    stored = await hass.async_add_executor_job(_write, path, body)
    state[model] = stored
    return stored
