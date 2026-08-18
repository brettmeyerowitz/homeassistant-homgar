"""Opt-in prompt tests (v3.0.44).

The prompt must appear exactly once for an existing install that has never
answered, and never again once any choice — including "no" — is recorded.
A nagging privacy prompt is worse than no prompt.

Also pins the fix for the re-nag bug (final review, IMPORTANT 2): a user who
merely DISMISSES the notification (never submits a choice via Options) must
still never see it again. The old guard only checked for a recorded choice,
so dismissing did nothing and the prompt reappeared on every restart/reload
forever — directly contradicting what the message told the user. The fix
persists a "prompted" flag the moment the notification is shown.

Runs in the ha-test container against the deployed integration at /config.
"""
import asyncio
import sys
import types

sys.path.insert(0, "/config")

from custom_components.homgar import telemetry  # noqa: E402
from custom_components.homgar.const import CONF_TELEMETRY_CHOICE  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


class _FakeEntry:
    def __init__(self, options=None, entry_id="entry_abc"):
        self.options = dict(options or {})
        self.entry_id = entry_id
        self.title = "HomGar"


class _FakeHass:
    """Telemetry storage is fully in-memory — see the monkeypatched
    _async_store_load/save below, which back onto this instance's `_disk`
    dict rather than touching real HA storage."""
    def __init__(self, seed=None):
        self.data = {}
        self._disk = dict(seed or {})


async def _fake_store_load(hass):
    return dict(hass._disk)


async def _fake_store_save(hass, data):
    hass._disk = dict(data)


telemetry._async_store_load = _fake_store_load  # type: ignore[attr-defined]
telemetry._async_store_save = _fake_store_save  # type: ignore[attr-defined]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


created = []


def _fake_create(hass, message, title=None, notification_id=None):
    created.append({"message": message, "title": title, "id": notification_id})


telemetry._async_create_notification = _fake_create  # type: ignore[attr-defined]

# unset -> prompt
created.clear()
hass = _FakeHass()
shown = run(telemetry.async_prompt_for_telemetry_once(hass, _FakeEntry()))
check("prompts when the choice has never been made", shown is True and len(created) == 1)
check("uses a stable notification id",
      created[0]["id"] == "homgar_telemetry_optin", str(created[0]["id"]))
check("the prompt says it is optional and off by default",
      "optional" in created[0]["message"].lower()
      and "off by default" in created[0]["message"].lower())
check("the prompt links to the integration settings",
      "/config/integrations" in created[0]["message"])
check("the prompt discloses that versions are included",
      "version" in created[0]["message"].lower())
check("the prompt no longer falsely claims it will never ask again "
      "(it can, if dismissed — the fix corrects the wording instead)",
      "will not ask again" not in created[0]["message"].lower())

# answered yes -> silent
created.clear()
shown = run(telemetry.async_prompt_for_telemetry_once(
    _FakeHass(), _FakeEntry({CONF_TELEMETRY_CHOICE: True})))
check("never prompts again once opted in", shown is False and created == [])

# answered no -> silent (the important case: declining must not nag)
created.clear()
shown = run(telemetry.async_prompt_for_telemetry_once(
    _FakeHass(), _FakeEntry({CONF_TELEMETRY_CHOICE: False})))
check("never prompts again once declined", shown is False and created == [])

# --- IMPORTANT 2 regression: dismissing (no choice recorded) still stops it
created.clear()
hass_dismiss = _FakeHass()
entry_dismiss = _FakeEntry({}, entry_id="entry_dismiss")
first = run(telemetry.async_prompt_for_telemetry_once(hass_dismiss, entry_dismiss))
second = run(telemetry.async_prompt_for_telemetry_once(hass_dismiss, entry_dismiss))
check("prompting twice in a row (simulating dismiss + restart, still no "
      "choice recorded in options) shows the notification only once",
      first is True and second is False and len(created) == 1,
      f"first={first} second={second} created={len(created)}")

# A THIRD call (e.g. another reload) must also stay silent — this is the
# permanent-suppression guarantee, not a one-off coincidence.
third = run(telemetry.async_prompt_for_telemetry_once(hass_dismiss, entry_dismiss))
check("stays silent on a third call too", third is False and len(created) == 1)

# The "prompted" flag must be scoped per config entry — a second entry
# (second account) that has never been prompted must still see it.
created.clear()
entry_other = _FakeEntry({}, entry_id="entry_other_account")
shown_other = run(telemetry.async_prompt_for_telemetry_once(hass_dismiss, entry_other))
check("a different config entry is prompted independently",
      shown_other is True and len(created) == 1)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
