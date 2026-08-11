"""Options-flow section/flattening tests (final review, UI fix).

The three telemetry toggles used to fake indentation with literal `└`
characters in translations/en.json. The fix groups the two sub-toggles
under a proper `section` (HA >= 2024.6) and drops the fake indentation
everywhere, including in the fallback used on cores below that floor
(hacs.json declares a minimum of 2024.5.0 — an unconditional `section`
import would break setup there, the same class of problem as UnitOfRatio,
see sensor_defs.py and issue #84).

Because `section` nests submitted values under its own key, the options
flow must flatten them back out before async_create_entry so the stored
option keys stay exactly telemetry_choice / telemetry_share_country /
telemetry_share_models regardless of which UI shape produced them, and
existing entries with flat options (written before this fix, or by a core
that never had `section`) must keep working unchanged.

Runs in the ha-test container against the deployed integration at /config.
"""
import sys

sys.path.insert(0, "/config")

from custom_components.homgar.config_flow import (  # noqa: E402
    _TELEMETRY_SECTION_KEY,
    _build_options_schema,
    _flatten_telemetry_section,
    section as real_section,
)
from custom_components.homgar.const import (  # noqa: E402
    CONF_GROUP_MULTI_ZONE_DEVICES,
    CONF_TELEMETRY_CHOICE,
    CONF_TELEMETRY_COUNTRY,
    CONF_TELEMETRY_MODELS,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


# --- flattening --------------------------------------------------------
nested_input = {
    CONF_GROUP_MULTI_ZONE_DEVICES: False,
    CONF_TELEMETRY_CHOICE: True,
    _TELEMETRY_SECTION_KEY: {
        CONF_TELEMETRY_COUNTRY: True,
        CONF_TELEMETRY_MODELS: False,
    },
}
flattened = _flatten_telemetry_section(nested_input)
check("the section key is removed after flattening",
      _TELEMETRY_SECTION_KEY not in flattened, str(flattened))
check("sub-toggle values are hoisted to the plain flat keys",
      flattened.get(CONF_TELEMETRY_COUNTRY) is True
      and flattened.get(CONF_TELEMETRY_MODELS) is False,
      str(flattened))
check("keys outside the section are left untouched",
      flattened.get(CONF_TELEMETRY_CHOICE) is True
      and flattened.get(CONF_GROUP_MULTI_ZONE_DEVICES) is False,
      str(flattened))
check("flattening never mutates the caller's dict",
      _TELEMETRY_SECTION_KEY in nested_input,
      "input dict was mutated in place")

flat_input = {
    CONF_GROUP_MULTI_ZONE_DEVICES: True,
    CONF_TELEMETRY_CHOICE: False,
    CONF_TELEMETRY_COUNTRY: False,
    CONF_TELEMETRY_MODELS: False,
}
flattened_noop = _flatten_telemetry_section(flat_input)
check("flat input (no section key — legacy entries / HA < 2024.6 submissions) "
      "passes through unchanged",
      flattened_noop == flat_input, str(flattened_noop))

# --- schema: fallback path (section unavailable) ------------------------
fallback_schema = _build_options_schema({}, section_impl=None)
fallback_keys = {str(k) for k in fallback_schema.schema}
check("fallback schema exposes the sub-toggles as flat top-level keys",
      CONF_TELEMETRY_COUNTRY in fallback_keys and CONF_TELEMETRY_MODELS in fallback_keys,
      str(fallback_keys))
check("fallback schema has no section key at all",
      _TELEMETRY_SECTION_KEY not in fallback_keys, str(fallback_keys))

# --- schema: section path (section available) ---------------------------
check("`section` imported successfully in this test environment "
      "(HA >= 2024.6 is what the ha-test container runs)",
      real_section is not None)

if real_section is not None:
    section_schema = _build_options_schema({}, section_impl=real_section)
    section_keys = {str(k) for k in section_schema.schema}
    check("section-path schema nests the sub-toggles under the section key "
          "instead of exposing them flat",
          _TELEMETRY_SECTION_KEY in section_keys
          and CONF_TELEMETRY_COUNTRY not in section_keys
          and CONF_TELEMETRY_MODELS not in section_keys,
          str(section_keys))
    check("the master switch stays outside the section either way",
          CONF_TELEMETRY_CHOICE in section_keys, str(section_keys))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
