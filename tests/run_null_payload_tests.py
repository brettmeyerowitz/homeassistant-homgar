"""Regression tests: a null ``data`` payload must not crash the coordinator.

Issue #97: an account containing an HCS048B (a Bluetooth water flow meter) could
not set up at all. ``getDeviceStatus`` answers ``{"code": 0, "msg": "SUCCESS",
"data": null}`` for a device that has no hub-side status, because a Bluetooth
device's readings only reach the cloud when the phone app uploads them via
``/app/device/coap/state`` — the cloud is a passive mirror, not a live source.

``data.get("data", {})`` does not defend against that: a dict default only
applies when the key is *absent*, and here it is present and null. The client
therefore returned ``None``, the coordinator stored it, and the next loop raised
``AttributeError: 'NoneType' object has no attribute 'get'`` — turning a device
we simply cannot read into a setup-blocking crash loop.

The invariant this locks down: ``_response_payload`` never returns None, so no
caller can inherit that crash, whatever the cloud sends.

Runs in the ha-test container against the deployed integration at /config.
"""
import sys

sys.path.insert(0, "/config")

from custom_components.homgar.api.client import _response_payload  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✅ {name}"); PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}"); FAIL += 1


print("\n🧪 _response_payload — an explicit null must not leak through as None")

# The exact #97 response.
crash_response = {"code": 0, "msg": "SUCCESS", "data": None, "ts": 1787914495010}
check(
    "the #97 response yields the default, not None",
    _response_payload(crash_response, {}) == {},
    f"got {_response_payload(crash_response, {})!r}",
)
# And the result is safe to use the way the coordinator uses it — this is the
# call that actually raised AttributeError at coordinator.py:362.
check(
    "the result supports .get() as the coordinator expects",
    _response_payload(crash_response, {}).get("subDeviceStatus", []) == [],
)
check(
    "a missing key still yields the default",
    _response_payload({"code": 0}, {}) == {},
)
check(
    "a list default is honoured for null",
    _response_payload({"code": 0, "data": None}, []) == [],
)

print("\n🧪 _response_payload — real payloads pass through untouched")

check(
    "a populated dict payload passes through",
    _response_payload({"data": {"subDeviceStatus": [1]}}, {}) == {"subDeviceStatus": [1]},
)
check(
    "a populated list payload passes through",
    _response_payload({"data": [{"mid": 1}]}, []) == [{"mid": 1}],
)
# Falsy-but-real answers must be preserved. Substituting the default here would
# silently rewrite "the server said empty" into "the server said nothing",
# which is a different fact and would mask genuine empty responses.
check(
    "an empty dict payload is preserved, not replaced",
    _response_payload({"data": {}}, {"x": 1}) == {},
    f"got {_response_payload({'data': {}}, {'x': 1})!r}",
)
check(
    "an empty list payload is preserved, not replaced",
    _response_payload({"data": []}, [{"x": 1}]) == [],
    f"got {_response_payload({'data': []}, [{'x': 1}])!r}",
)
check(
    "a zero payload is preserved, not replaced",
    _response_payload({"data": 0}, {}) == 0,
    f"got {_response_payload({'data': 0}, {})!r}",
)

print("\n🧪 the invariant: never None, whatever the cloud sends")

for envelope in (
    {"data": None},
    {},
    {"data": {}},
    {"data": []},
    {"code": 0, "msg": "SUCCESS", "data": None, "ts": 1},
):
    check(
        f"never None for {envelope!r}",
        _response_payload(envelope, {}) is not None,
    )


print("\n" + "=" * 50)
print(f"Results: {PASS}/{PASS + FAIL} passed, {FAIL} failed")
if FAIL:
    print("❌ TESTS FAILED")
    sys.exit(1)
print("✅ ALL TESTS PASSED")
