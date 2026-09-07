"""Product photograph for each device.

Home Assistant's image platform serves the bytes itself, so the integration
needs no HTTP view of its own and ``entity_picture`` never points at the
vendor's CDN — a dashboard render tells oss3.homgarus.com nothing about who is
looking or when. The photo is fetched once per model, ever, and cached on disk.

One image entity per device, deliberately. Setting ``entity_picture`` on the
shared sensor base would stamp the same photo on every battery, signal,
temperature and moisture row, replacing the state icons that make a device page
readable.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .product_images import async_ensure_cached, image_url_for_model
from .hub_entities import _hub_model
from .sensor import build_device_info

_LOGGER = logging.getLogger(__name__)


class HomGarProductImage(CoordinatorEntity, ImageEntity):
    """The vendor's product photograph for one device."""

    _attr_content_type = "image/png"
    _attr_should_poll = False
    _attr_name = "Product image"
    # Keeps the photo out of the device's main sensor list.
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = True

    def __init__(self, hass, coordinator, sensor_key: str, sensor_info: dict, base_slug: str) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        # Entity.hass is normally assigned when HA adds the entity to a
        # platform; set it here so the entity is usable as soon as it is built.
        self.hass = hass
        self._sensor_key = sensor_key
        self._sensor_info = sensor_info
        self._base_slug = base_slug
        self._attr_unique_id = f"{sensor_info['mid']}_{sensor_info['addr']}_product_image"

    @property
    def device_info(self) -> dict[str, Any]:
        return build_device_info(self.coordinator, self._sensor_info)

    async def async_image(self) -> bytes | None:
        """Return the cached photo, fetching it once if it isn't cached yet."""
        model = self._sensor_info.get("model") or ""
        session = None
        if image_url_for_model(model):
            try:
                session = async_get_clientsession(self.hass)
            except Exception:  # noqa: BLE001 - no session in tests; the cache may still hold it
                session = None
        path = await async_ensure_cached(self.hass, session, model)
        if not path:
            return None
        # The entity's state is the image's last-updated time; without one it
        # reads "Unknown" even while serving bytes perfectly well.
        if self._attr_image_last_updated is None:
            self._attr_image_last_updated = dt_util.utcnow()
        try:
            return await self.hass.async_add_executor_job(_read, path)
        except Exception as exc:  # noqa: BLE001 - a missing picture must never break the entity
            _LOGGER.debug("Could not read cached product image for %s: %s", model, exc)
            return None


def _read(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


class HomGarHubProductImage(HomGarProductImage):
    """The same photo, for a hub.

    Hubs live in coordinator.data["hubs"], not ["sensors"], and are their own
    devices — so they need their own pass. Attaching by identifiers alone lets
    Home Assistant merge this onto the existing hub device without this class
    having to restate (and risk contradicting) the hub's device metadata.
    """

    def __init__(self, hass, coordinator, hub_info: dict) -> None:
        model = _hub_model(hub_info) or ""
        sensor_info = {"mid": hub_info.get("mid"), "addr": "hub", "model": model}
        super().__init__(hass, coordinator, "hub", sensor_info, "hub")
        self._hub_info = hub_info
        self._attr_unique_id = f"rainpoint_hub_{hub_info.get('mid')}_product_image"

    @property
    def device_info(self) -> dict[str, Any]:
        return {"identifiers": {(DOMAIN, f"rainpoint_hub_{self._hub_info['mid']}")}}


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Create one product image entity per device."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data["coordinator"]

    entities: list[HomGarProductImage] = []
    for sensor_key, info in (coordinator.data.get("sensors") or {}).items():
        sensor_info = info.get("info") if isinstance(info, dict) and "info" in info else info
        if not isinstance(sensor_info, dict):
            continue
        if not image_url_for_model(sensor_info.get("model") or ""):
            continue
        entities.append(
            HomGarProductImage(hass, coordinator, sensor_key, sensor_info, sensor_key)
        )

    hubs_cfg = coordinator.data.get("hubs") or []
    hubs = hubs_cfg.values() if isinstance(hubs_cfg, dict) else hubs_cfg
    for hub_info in hubs:
        if not isinstance(hub_info, dict):
            continue
        if not image_url_for_model(_hub_model(hub_info) or ""):
            continue
        entities.append(HomGarHubProductImage(hass, coordinator, hub_info))

    if entities:
        async_add_entities(entities)
