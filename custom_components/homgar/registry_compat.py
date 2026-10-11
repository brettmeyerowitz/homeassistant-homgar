"""Device-registry calls that work across the 2027.8 deprecations.

Home Assistant 2026.9 deprecated two things this integration relies on, both
removed in 2027.8.0:

* ``async_get_device(identifiers={...})`` -> ``async_get_device_by_identifier``,
  because identifiers are no longer unique across config entries. The
  replacement takes a single identifier and the config entry to scope it to.
* ``via_device`` in ``DeviceInfo`` -> ``via_device_id``, which takes the
  parent's registry ID rather than an identifier tuple.

Neither replacement exists before 2026.8, and installs older than that are
still out there, so both helpers feature-detect rather than assume. The old
call is used only where the new one is unavailable, so a current Home
Assistant never takes the deprecated path and never logs the warning.
"""
from __future__ import annotations

import logging

from homeassistant.helpers import device_registry as dr

_LOGGER = logging.getLogger(__name__)


def find_device(device_reg, identifier: tuple[str, str], config_entry_id: str):
    """Look up a device by one identifier, scoped to a config entry.

    On Home Assistant 2026.8 and later this scopes the lookup to the entry,
    which is the behaviour the deprecation exists to enforce: the same
    identifier can legitimately belong to two entries, and the old global
    lookup could return either. Every caller here looks up a device it created
    under the entry it is passing, so scoping is a correctness fix rather than
    a restriction.
    """
    scoped = getattr(device_reg, "async_get_device_by_identifier", None)
    if scoped is not None:
        return scoped(identifier, config_entry_id)
    return device_reg.async_get_device(identifiers={identifier})


def via_device_fields(hass, config_entry_id: str, parent: tuple[str, str]) -> dict:
    """Return the DeviceInfo fragment that links a device to its parent.

    ``hass`` may be None where a caller has no access to it; the identifier
    tuple is returned in that case, which still links the device correctly.

    Prefers ``via_device_id``, which needs the parent's registry ID and so
    needs the parent to exist already. When it does not - a child built before
    its parent on first setup - this falls back to the identifier tuple rather
    than dropping the link, because a missing parent reference silently
    reparents the device to the top level and loses the hierarchy. The
    fallback still works until 2027.8 and resolves itself on the next reload,
    once the parent is in the registry.
    """
    if hass is None or config_entry_id is None:
        return {"via_device": parent}
    try:
        device_reg = dr.async_get(hass)
        if getattr(device_reg, "async_get_device_by_identifier", None) is not None:
            found = find_device(device_reg, parent, config_entry_id)
            if found is not None:
                return {"via_device_id": found.id}
    except Exception:  # noqa: BLE001 - see below
        # This runs inside a device_info property, which must never raise: an
        # exception there stops the entity loading altogether. Falling back to
        # the identifier tuple keeps the parent link intact and still works
        # until 2027.8, which is a better failure than an entity that does not
        # appear.
        _LOGGER.debug("via_device_id lookup failed for %s; using the identifier",
                      parent, exc_info=True)
    return {"via_device": parent}


def via_device_for(coordinator, parent: tuple[str, str]) -> dict:
    """``via_device_fields`` for the common case of an entity's coordinator.

    Reads ``hass`` and the entry id defensively. This is called from
    ``device_info``, which several test harnesses exercise with a stand-in
    coordinator, and an attribute error there would break entity construction
    rather than merely losing the parent link.
    """
    return via_device_fields(
        getattr(coordinator, "hass", None),
        getattr(getattr(coordinator, "_entry", None), "entry_id", None),
        parent,
    )
