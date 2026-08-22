"""Regression tests: API failures reach automations as Home Assistant errors.

Issue #82 follow-up. A live report on 2026-08-18 (07:00 CEST) showed the gap:
a `valve.open_valve` action configured with

    action: valve.open_valve
    target:
      entity_id: "{{ ventil }}"
    continue_on_error: true

aborted the whole automation with "Unexpected error for call_service" when the
write exhausted its safe retries, so the user's own safety branch — which would
have closed the already-open master valve — never ran.

That is not a retry-policy problem. Home Assistant's script engine decides what
`continue_on_error` may swallow in `homeassistant/helpers/script.py`
(`_Script._handle_exception`): `_HaltScript` and a short list of
"incorrect script" errors always re-raise, and then

    # Only Home Assistant errors can be ignored.
    if not isinstance(exception, HomeAssistantError):
        raise exception

`HomGarApiError` derived straight from `Exception`, so every failed valve,
switch or control command in this integration was unhandleable by an
automation — the transient case is simply the one that shows up in the field.

These tests pin the exception hierarchy that guarantee rests on, and check it
end to end through the real write path: what an automation actually receives
when the cloud is unreachable must be a `HomeAssistantError`.

Runs on the host and in the ha-test container, stdlib only. Where Home
Assistant is importable (the container) the checks run against the *real*
`HomeAssistantError`; on a bare host a faithful stub stands in.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _find_repo_root() -> Path:
    candidates = [Path(__file__).resolve().parent, Path.cwd(), Path("/config")]
    for start in candidates:
        current = start
        while True:
            if (current / "custom_components" / "homgar" / "api" / "client.py").exists():
                return current
            if current.parent == current:
                break
            current = current.parent
    raise RuntimeError("Could not locate repository root containing custom_components/homgar")


ROOT = _find_repo_root()


def _load_module(module_name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# --- HomeAssistantError: the real one where it exists ----------------------
# Imported BEFORE aiohttp is stubbed: homeassistant.exceptions pulls
# ClientResponse from the real aiohttp, so stubbing first would force every run
# down the fallback branch and quietly stop testing the genuine class.
# In the ha-test container Home Assistant is installed, and asserting against
# the genuine class is the whole point. On a bare host we register a stub that
# mirrors it (HomeAssistantError derives from Exception; ServiceValidationError
# from HomeAssistantError) so the suite still runs, and say so in the output.

try:  # pragma: no cover - depends on the environment, both branches exercised
    from homeassistant.exceptions import HomeAssistantError  # type: ignore
    _HA_IS_REAL = True
except ImportError:
    _ha_pkg = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    _exc_stub = types.ModuleType("homeassistant.exceptions")
    _exc_stub.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    _exc_stub.ServiceValidationError = type(
        "ServiceValidationError", (_exc_stub.HomeAssistantError,), {})
    _exc_stub.ConditionError = type("ConditionError", (_exc_stub.HomeAssistantError,), {})
    _ha_pkg.exceptions = _exc_stub
    sys.modules["homeassistant.exceptions"] = _exc_stub
    HomeAssistantError = _exc_stub.HomeAssistantError
    _HA_IS_REAL = False

# --- aiohttp stub -----------------------------------------------------------
# Only the pieces client.py touches at import time plus the one connect-phase
# error these tests raise. The full hierarchy is pinned by
# run_write_presend_retry_tests.py; duplicating it here would add nothing.


class _ClientTimeout:
    def __init__(self, total=None, connect=None, sock_connect=None, sock_read=None):
        self.total = total
        self.connect = connect


_aiohttp_stub = types.ModuleType("aiohttp")
_aiohttp_stub.ClientTimeout = _ClientTimeout
_aiohttp_stub.ClientSession = type("ClientSession", (), {})
_aiohttp_stub.ClientError = type("ClientError", (Exception,), {})
_aiohttp_stub.ClientConnectionError = type(
    "ClientConnectionError", (_aiohttp_stub.ClientError,), {})
_aiohttp_stub.ClientOSError = type(
    "ClientOSError", (_aiohttp_stub.ClientConnectionError, OSError), {})
_aiohttp_stub.ClientConnectorError = type(
    "ClientConnectorError", (_aiohttp_stub.ClientOSError,), {})
_aiohttp_stub.ServerConnectionError = type(
    "ServerConnectionError", (_aiohttp_stub.ClientConnectionError,), {})
_aiohttp_stub.ServerDisconnectedError = type(
    "ServerDisconnectedError", (_aiohttp_stub.ServerConnectionError,), {})
_aiohttp_stub.ServerTimeoutError = type(
    "ServerTimeoutError", (_aiohttp_stub.ServerConnectionError, asyncio.TimeoutError), {})
_aiohttp_stub.ConnectionTimeoutError = type(
    "ConnectionTimeoutError", (_aiohttp_stub.ServerTimeoutError,), {})
_aiohttp_stub.SocketTimeoutError = type(
    "SocketTimeoutError", (_aiohttp_stub.ServerTimeoutError,), {})
sys.modules["aiohttp"] = _aiohttp_stub


sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
sys.modules.setdefault("custom_components.homgar", types.ModuleType("custom_components.homgar"))
sys.modules.setdefault("custom_components.homgar.api", types.ModuleType("custom_components.homgar.api"))
_load_module("custom_components.homgar.const", "custom_components/homgar/const.py")
client_mod = _load_module("custom_components.homgar.api.client", "custom_components/homgar/api/client.py")

import aiohttp  # the stub registered above  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        print(f"  ✅ {name}")
        PASS += 1
    else:
        print(f"  ❌ {name}{': ' + detail if detail else ''}")
        FAIL += 1


# --- the hierarchy ----------------------------------------------------------


def _test_hierarchy():
    check("HomGarApiError is a HomeAssistantError (continue_on_error can see it)",
          issubclass(client_mod.HomGarApiError, HomeAssistantError),
          f"bases={client_mod.HomGarApiError.__bases__}")
    check("HomGarTransientError is a HomeAssistantError",
          issubclass(client_mod.HomGarTransientError, HomeAssistantError),
          f"mro={[c.__name__ for c in client_mod.HomGarTransientError.__mro__]}")
    # The coordinator (coordinator.py) and config flow both catch HomGarApiError
    # and rely on the transient flavour being one; widening the base must not
    # quietly break that.
    check("HomGarTransientError is still a HomGarApiError",
          issubclass(client_mod.HomGarTransientError, client_mod.HomGarApiError))
    check("a plain Exception is still not a HomeAssistantError (control)",
          not issubclass(Exception, HomeAssistantError))


# --- Home Assistant's own continue_on_error rule ----------------------------


def _ha_would_continue(exc: BaseException) -> bool:
    """Mirror of the decision in `Script._handle_exception` (helpers/script.py).

    Reproduced rather than imported because the real one needs a running hass;
    the single rule that matters here is its last line — only HomeAssistantError
    subclasses may be swallowed by `continue_on_error`.
    """
    return isinstance(exc, HomeAssistantError)


def _test_continue_on_error_rule():
    exhausted = client_mod.HomGarTransientError(
        "controlWorkMode: Connection timeout to host "
        "https://region3.homgarus.com/app/device/controlWorkMode"
    )
    check("an exhausted transient write is swallowed by continue_on_error",
          _ha_would_continue(exhausted) is True)
    check("a genuine API error is swallowed too (automation keeps its safety branch)",
          _ha_would_continue(client_mod.HomGarApiError("controlWorkMode HTTP 404")) is True)
    check("an unrelated bug is NOT swallowed (still surfaces as unexpected)",
          _ha_would_continue(ValueError("programming error")) is False)


# --- end to end through the real write path ---------------------------------


_LOGIN_PAYLOAD = {
    "code": 0, "ts": 1700000000000,
    "data": {"token": "fresh", "refreshToken": "r", "tokenExpired": 3600, "user": {}},
}
_CTL = "/app/device/controlWorkMode"


class _FakeReqCtx:
    def __init__(self, action):
        self._action = action

    async def __aenter__(self):
        if isinstance(self._action, BaseException):
            raise self._action
        status, payload = self._action

        class _Resp:
            status = None
            async def json(self_inner):
                return payload

        resp = _Resp()
        resp.status = status
        return resp

    async def __aexit__(self, *exc):
        return False


class _ScriptedSession:
    def __init__(self, script):
        self._script = {k: list(v) for k, v in script.items()}
        self.calls = []

    def _next(self, method, url):
        self.calls.append((method, url))
        if url.endswith("/auth/basic/app/login"):
            return _FakeReqCtx((200, _LOGIN_PAYLOAD))
        for suffix, actions in self._script.items():
            if url.endswith(suffix) and actions:
                return _FakeReqCtx(actions.pop(0))
        raise AssertionError(f"No scripted action for {method} {url}")

    def get(self, url, **kwargs):
        return self._next("get", url)

    def post(self, url, **kwargs):
        return self._next("post", url)


def _make_client(script):
    session = _ScriptedSession(script)
    client = client_mod.HomGarClient("31", "a@b.com", "pw", session, "homgar")
    client._token = "tok"
    client._refresh_token = "r"
    client._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return client, session


async def _fake_sleep(delay):
    return None


async def _test_open_valve_raises_ha_error():
    """The reported scenario, start to finish: both safe attempts hit a connect
    timeout, so the command genuinely failed — and what the automation receives
    must be catchable."""
    err = aiohttp.ConnectionTimeoutError(
        f"Connection timeout to host https://region3.homgarus.com{_CTL}")
    client, session = _make_client({_CTL: [err] * 5})
    raised = None
    try:
        await client.control_work_mode(
            mid=1, addr=2, device_name="d", product_key="p", port=1, mode=1, duration=60,
        )
    except BaseException as exc:  # noqa: BLE001 - the point is what type escapes
        raised = exc
    check("an exhausted valve open still raises",
          raised is not None)
    check("what reaches the automation is a HomeAssistantError",
          isinstance(raised, HomeAssistantError), f"got {type(raised).__name__}")
    check("continue_on_error would let the safety branch run",
          _ha_would_continue(raised) is True, f"got {type(raised).__name__}")
    check("the failure is still identifiable as transient",
          isinstance(raised, client_mod.HomGarTransientError), f"got {type(raised).__name__}")
    check("the cloud host and endpoint stay in the message",
          "controlWorkMode" in str(raised), str(raised))
    # The attempt count itself is not the guarantee — the classifier is. This
    # failure is a connect timeout, which is provably pre-send, so every attempt
    # in the envelope is safe. What must never change is that the count is
    # bounded and derived from the declared envelope rather than unbounded.
    # (The envelope widened in issue #82's second field report; its shape is
    # owned by run_write_retry_envelope_tests.py.)
    expected = len(client_mod._WRITE_PRE_SEND_RETRY_BACKOFF) + 1
    check(f"the write envelope stays bounded ({expected} attempts, not more)",
          sum(1 for _m, url in session.calls if url.endswith(_CTL)) == expected,
          str(session.calls))


def main() -> int:
    print("Service-error surface tests (issue #82 follow-up)")
    print(f"  (HomeAssistantError source: {'real homeassistant' if _HA_IS_REAL else 'stub'})")
    _test_hierarchy()
    _test_continue_on_error_rule()
    original_sleep = client_mod.asyncio.sleep
    client_mod.asyncio.sleep = _fake_sleep
    try:
        asyncio.run(_test_open_valve_raises_ha_error())
    finally:
        client_mod.asyncio.sleep = original_sleep
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
