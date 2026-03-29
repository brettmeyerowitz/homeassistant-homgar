"""Switch entities for HomGar integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .debug import HomGarDebugSwitchEntity
from .coordinator import HomGarCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HomGar switch entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HomGarCoordinator = data["coordinator"]

    entities = []

    # Add debug switch
    debug_switch = HomGarDebugSwitchEntity(hass, coordinator, entry)
    entities.append(debug_switch)

    _LOGGER.info(f"Added {len(entities)} switch entities")
    async_add_entities(entities)
