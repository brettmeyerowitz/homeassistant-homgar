"""Tests for the diagnostics platform's redaction and summarisation.

Diagnostics exist to be pasted into public GitHub issues, so the redaction set is
a privacy boundary, not a nicety: anything identifying the account or usable as a
device credential must never survive a download. Equally, over-redacting destroys
the reason the download exists — ``model``, ``modelCode`` and the raw payload
frames are the diagnostic payload itself, and blanking them would leave us asking
for hand-pasted logs all over again (which is how issue #97 stalled).

``mid`` is deliberately kept: it is a device identifier rather than a credential,
and retaining it lets a maintainer correlate devices across a long issue thread.

Runs in the ha-test container against the deployed integration at /config.
"""
import sys

sys.path.insert(0, "/config")

from custom_components.homgar.diagnostics import (  # noqa: E402
    TO_REDACT,
    _catalogue_summary,
    _redact,
    _unknown_models,
)

PASS = 0
FAIL = 0
R = "**REDACTED**"


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


print("\n🧪 _redact — credentials and account identifiers must not survive")

for field in ("email", "password", "token", "refreshToken", "deviceId",
              "iotId", "productKey", "deviceName", "mac", "hid"):
    check(f"{field} is redacted", _redact({field: "secret"})[field] == R,
          f"got {_redact({field: 'secret'})[field]!r}")

# Redaction must reach into the nested shapes the cloud actually returns:
# hubs carry subDevices, and status envelopes nest under "data".
nested = {"data": {"hubs": [{"mid": 1, "iotId": "abc", "subDevices": [{"mac": "aa:bb"}]}]}}
out = _redact(nested)
check(
    "nested list-of-dicts is redacted",
    out["data"]["hubs"][0]["subDevices"][0]["mac"] == R,
    f"got {out['data']['hubs'][0]['subDevices'][0]['mac']!r}",
)
check("nested dict is redacted", out["data"]["hubs"][0]["iotId"] == R)


print("\n🧪 _redact — diagnostic value must be preserved")

# These are the whole point of the download. Redacting them would make the
# artefact useless for device-support work.
keep = {
    "mid": 356840,
    "model": "HCS048B",
    "modelCode": 283,
    "softVer": "1.1.1041",
    "value": "10#E1BB00DC01856002881EC6500000FF0FCD31391A",
    "subDeviceStatus": [{"id": "D01", "value": "10#ABC"}],
}
kept = _redact(keep)
check("mid is kept (identifier, not credential)", kept["mid"] == 356840)
check("model is kept", kept["model"] == "HCS048B")
check("modelCode is kept", kept["modelCode"] == 283)
check("softVer is kept", kept["softVer"] == "1.1.1041")
check("raw payload frame is kept", kept["value"] == keep["value"])
check("nested payload frame is kept", kept["subDeviceStatus"][0]["value"] == "10#ABC")

# A null status is the #97 signature and must reach us intact, not normalised.
null_env = _redact({"code": 0, "msg": "SUCCESS", "data": None, "ts": 1})
check("an explicit null data is preserved verbatim", null_env["data"] is None)
check("the response code is preserved", null_env["code"] == 0)

check("mid is not in the redaction set", "mid" not in TO_REDACT)

# Regression: key-based redaction cannot see an identifier embedded in free
# text. The config entry title is built as "HomGar/RainPoint (<email>)", so a
# real download leaked the account email even though "email" was redacted —
# caught by auditing an actual downloaded file rather than trusting the key set.
leaky_title = "HomGar/RainPoint (someone@example.com)"
check(
    "entry title is redacted (it embeds the account email)",
    _redact({"title": leaky_title})["title"] == R,
    f"got {_redact({'title': leaky_title})['title']!r}",
)
check("title is in the redaction set", "title" in TO_REDACT)


print("\n🧪 _catalogue_summary — how stale is this install's catalogue?")

summary = _catalogue_summary()
check("reports a catalogue version", summary.get("version") is not None)
check("reports a model count", isinstance(summary.get("model_count"), int)
      and summary["model_count"] > 0, f"got {summary.get('model_count')!r}")


print("\n🧪 _unknown_models — name hardware our catalogue has never seen")

hubs = [
    {"model": "HWG023WRF", "subDevices": [{"model": "HCS012ARF"}]},
    {"model": "HZZ999NEW", "subDevices": [{"model": "HQQ000ALSONEW"}]},
]
unknown = _unknown_models(hubs)
check("an unknown hub model is reported", "HZZ999NEW" in unknown, f"got {unknown!r}")
check("an unknown sub-device model is reported", "HQQ000ALSONEW" in unknown)
check("a known hub model is not reported", "HWG023WRF" not in unknown)
check("a known sub-device model is not reported", "HCS012ARF" not in unknown)
check("result is sorted and deduplicated", unknown == sorted(set(unknown)))
check("no hubs yields no unknown models", _unknown_models([]) == [])


print("\n" + "=" * 50)
print(f"Results: {PASS}/{PASS + FAIL} passed, {FAIL} failed")
if FAIL:
    print("❌ TESTS FAILED")
    sys.exit(1)
print("✅ ALL TESTS PASSED")
