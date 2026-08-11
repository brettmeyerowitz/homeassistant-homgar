"""Opt-in prompt tests (v3.0.44).

The prompt must appear exactly once for an existing install that has never
answered, and never again once any choice — including "no" — is recorded.
A nagging privacy prompt is worse than no prompt.

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
    def __init__(self, options=None):
        self.options = dict(options or {})
        self.entry_id = "entry_abc"
        self.title = "HomGar"


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


created = []


def _fake_create(hass, message, title=None, notification_id=None):
    created.append({"message": message, "title": title, "id": notification_id})


telemetry._async_create_notification = _fake_create  # type: ignore[attr-defined]

# unset -> prompt
created.clear()
shown = run(telemetry.async_prompt_for_telemetry_once(object(), _FakeEntry()))
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

# answered yes -> silent
created.clear()
shown = run(telemetry.async_prompt_for_telemetry_once(
    object(), _FakeEntry({CONF_TELEMETRY_CHOICE: True})))
check("never prompts again once opted in", shown is False and created == [])

# answered no -> silent (the important case: declining must not nag)
created.clear()
shown = run(telemetry.async_prompt_for_telemetry_once(
    object(), _FakeEntry({CONF_TELEMETRY_CHOICE: False})))
check("never prompts again once declined", shown is False and created == [])

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
