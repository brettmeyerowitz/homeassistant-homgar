# Fix: "My Home" area recreated after integration reload (#70)

## Problem

A user who deletes the HomGar-created "My Home" area in Home Assistant finds it
recreated (and devices re-homed into it) after every reload of the integration.

Reported in #70. Related to but distinct from #63:

- **#63** (fixed in 3.0.37): a device manually moved to a *different* (non-null)
  area was reverted. Guard added: only assign when `area_id is None`.
- **#70**: deleting an area in HA nulls `area_id` on every device that was in it.
  That null re-triggers the "unseeded, please assign" path in
  `_assign_devices_to_areas`, which then `async_create`s the area again and
  reassigns the devices. The #63 guard does not help because the state genuinely
  is `area_id is None`.

## Root cause

`_assign_devices_to_areas` (`custom_components/homgar/__init__.py`) runs ~2s after
*every* setup/reload (via `_async_finalize_device_layout`). It explicitly:

```python
area = area_reg.async_get_area_by_name(home_name)
if not area:
    area = area_reg.async_create(home_name)   # recreates a deleted area
...
if device.area_id is None:
    device.area_id = area.id                  # re-homes the device
```

This is the **only** vector that resurrects a deleted area on reload. `suggested_area`
in `DeviceInfo` (present across the platforms and `_ensure_device_registry_parents`)
is **not** a reload vector: HA applies `suggested_area` only at initial device
*creation* (`device is None`), never re-applying it to an existing device whose
`area_id` was nulled. (`suggested_area` is separately deprecated and breaks in HA
2026.9 — tracked as a separate issue, out of scope here.)

## Design

**Rule:** the integration seeds areas only on the **first setup** of a config entry.
After that it never creates or (re)assigns areas.

### First-setup detection (no persistence)

At the top of `async_setup_entry`, before any devices are created:

```python
is_first_setup = not dr.async_get(hass).async_entries_for_config_entry(entry.entry_id)
```

Stash the boolean in `entry_data` so the delayed `_assign_devices_to_areas` reads it.

| Scenario | Device registry at setup start | `is_first_setup` | Area seeding |
|---|---|---|---|
| Fresh install | empty | True | seed + assign |
| Reload / HA restart | populated | False | skip |
| Delete area, then reload | populated | False | skip (stays gone) |
| Remove & re-add integration | empty (deleted with entry) | True | re-seed |

No `Store` and no `entry.data` writes — avoids the reload loop that
`entry.add_update_listener(async_reload_entry)` (line 236) would otherwise cause.

### What changes in `_assign_devices_to_areas`

Gate on `is_first_setup`:

- **Gated (first setup only):** area creation (`async_create`), hub `area_id`
  assignment, sensor area creation + assignment, zone child-device assignment.
- **Unconditional (every reload):** hub device **name/model backfill** (the #63
  backfill) must keep running.

Concretely: if `not is_first_setup`, skip all area create/assign work but still run
the name/model backfill in the hub loop; return early before the sensor/zone loops.

### New devices on an existing install

Still auto-grouped: a newly discovered physical device is *created* in the registry
with `suggested_area`, which HA honors at creation time. (This stops working when
2026.9 removes `suggested_area`; handled by the separate deprecation issue.)

### Migration for already-affected users

None required. Post-upgrade the area still exists (old code kept recreating it); the
next reload no longer recreates it, so one final manual delete makes it stay gone.

## Testing

Unit test in the existing `tests/run_*.py` style:

- `is_first_setup=False` + a device with `area_id is None` → no `async_create`, no
  area assignment.
- `is_first_setup=False` + hub device missing name/model → backfill still applied.
- `is_first_setup=True` + no existing area → area created and device assigned.

## Out of scope

- Removing `suggested_area` ahead of the HA 2026.9 deprecation (separate issue).
