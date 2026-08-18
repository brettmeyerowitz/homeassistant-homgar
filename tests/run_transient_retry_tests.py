"""Regression tests: the API client retries transient upstream failures.

Issue #82: intermittent connection timeouts, DNS timeouts and HTTP 503 from
region3.homgarus.com surfaced as hard coordinator errors (entities flicking
Unavailable, error-log spam) even though the RainPoint cloud recovered on its
own moments later. The client now retries transient network errors and 5xx
responses with a short backoff, only giving up (raising HomGarTransientError)
after the retries are exhausted. Non-transient responses (4xx) still raise
immediately, and clean 200s never retry.

This runner avoids pytest so it runs on the host and in the ha-test container
with only the standard library.
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


# --- Minimal aiohttp stub (aiohttp is not a test-env dependency) -------------


class _ClientTimeout:
    def __init__(self, total=None, connect=None, sock_connect=None, sock_read=None):
        self.total = total
        self.connect = connect


_aiohttp_stub = types.ModuleType("aiohttp")
_aiohttp_stub.ClientTimeout = _ClientTimeout
_aiohttp_stub.ClientSession = type("ClientSession", (), {})
_aiohttp_stub.ClientError = type("ClientError", (Exception,), {})
# Connection/DNS failures subclass ClientError, matching real aiohttp.
_aiohttp_stub.ClientConnectionError = type("ClientConnectionError", (_aiohttp_stub.ClientError,), {})
_aiohttp_stub.ClientConnectorError = type("ClientConnectorError", (_aiohttp_stub.ClientConnectionError,), {})
sys.modules["aiohttp"] = _aiohttp_stub

# client.py now imports HomeAssistantError (issue #82: only HomeAssistantError
# subclasses can be swallowed by an automation's continue_on_error). The real
# homeassistant.exceptions imports ClientResponse from aiohttp, which is stubbed
# above, so register a faithful stub of just that class instead.
if "homeassistant.exceptions" not in sys.modules:
    _ha_pkg = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    _ha_exc_stub = types.ModuleType("homeassistant.exceptions")
    _ha_exc_stub.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    _ha_pkg.exceptions = _ha_exc_stub
    sys.modules["homeassistant.exceptions"] = _ha_exc_stub

sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
sys.modules.setdefault("custom_components.homgar", types.ModuleType("custom_components.homgar"))
sys.modules.setdefault("custom_components.homgar.api", types.ModuleType("custom_components.homgar.api"))
_load_module("custom_components.homgar.const", "custom_components/homgar/const.py")
client_mod = _load_module("custom_components.homgar.api.client", "custom_components/homgar/api/client.py")


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


_LOGIN_PAYLOAD = {
    "code": 0, "ts": 1700000000000,
    "data": {"token": "fresh", "refreshToken": "r", "tokenExpired": 3600, "user": {}},
}


class _FakeResp:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def text(self):
        return ""


class _FakeReqCtx:
    """Async context manager whose entry either raises or yields a response."""

    def __init__(self, action):
        self._action = action  # Exception instance, or (status, payload) tuple

    async def __aenter__(self):
        if isinstance(self._action, BaseException):
            raise self._action
        status, payload = self._action
        return _FakeResp(status, payload)

    async def __aexit__(self, *exc):
        return False


class _ScriptedSession:
    """Serves a scripted queue of actions per URL suffix.

    Each action is either an Exception instance (raised on context entry, to
    simulate a connection/DNS failure) or a ``(status, payload)`` tuple.
    """

    def __init__(self, script: dict[str, list]):
        self._script = {k: list(v) for k, v in script.items()}
        self.calls: list[tuple[str, str]] = []

    def _next(self, method: str, url: str):
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


def _count(session, suffix):
    return sum(1 for _m, url in session.calls if url.endswith(suffix))


_LIST = "/app/member/appHome/list"


# --- sleep patch so backoff does not actually wait -------------------------

_SLEEPS: list[float] = []


async def _fake_sleep(delay):
    _SLEEPS.append(delay)


async def _test_retries_503_then_succeeds():
    _SLEEPS.clear()
    script = {_LIST: [(503, {}), (200, {"code": 0, "data": [{"hid": 1}]})]}
    client, session = _make_client(script)
    result = await client.list_homes()
    check("list_homes recovers after a 503 (returns homes)", result == [{"hid": 1}], f"got {result!r}")
    check("list_homes retried once after 503 (2 GETs)", _count(session, _LIST) == 2, str(session.calls))
    check("a backoff sleep happened between attempts", len(_SLEEPS) == 1, f"sleeps={_SLEEPS}")


async def _test_retries_connection_error_then_succeeds():
    _SLEEPS.clear()
    import aiohttp  # the stub registered above
    err = aiohttp.ClientConnectorError("Cannot connect to host region3.homgarus.com:443")
    script = {_LIST: [err, (200, {"code": 0, "data": []})]}
    client, session = _make_client(script)
    result = await client.list_homes()
    check("list_homes recovers after a connection error", result == [], f"got {result!r}")
    check("list_homes retried once after connection error (2 GETs)", _count(session, _LIST) == 2, str(session.calls))


async def _test_retries_timeout_then_succeeds():
    _SLEEPS.clear()
    script = {_LIST: [asyncio.TimeoutError("Connection timeout to host"), (200, {"code": 0, "data": []})]}
    client, session = _make_client(script)
    result = await client.list_homes()
    check("list_homes recovers after a connection timeout", result == [], f"got {result!r}")
    check("list_homes retried once after timeout (2 GETs)", _count(session, _LIST) == 2, str(session.calls))


async def _test_exhausts_retries_then_raises_transient():
    _SLEEPS.clear()
    # More 503s than there are attempts.
    script = {_LIST: [(503, {})] * 10}
    client, session = _make_client(script)
    raised = None
    try:
        await client.list_homes()
    except client_mod.HomGarApiError as err:
        raised = err
    check("persistent 503 eventually raises", raised is not None)
    check(
        "raised error is a HomGarTransientError",
        isinstance(raised, client_mod.HomGarTransientError),
        f"got {type(raised).__name__}",
    )
    attempts = _count(session, _LIST)
    check("gave up after a bounded number of attempts (2-5)", 2 <= attempts <= 5, f"attempts={attempts}")
    check("slept once fewer than attempts (no sleep after final try)", len(_SLEEPS) == attempts - 1,
          f"attempts={attempts} sleeps={_SLEEPS}")
    check("backoff is non-decreasing (exponential-ish)", _SLEEPS == sorted(_SLEEPS), f"sleeps={_SLEEPS}")


async def _test_4xx_raises_immediately_without_retry():
    _SLEEPS.clear()
    script = {_LIST: [(404, {})]}
    client, session = _make_client(script)
    raised = None
    try:
        await client.list_homes()
    except client_mod.HomGarApiError as err:
        raised = err
    check("a 404 raises HomGarApiError", raised is not None)
    check("a 404 is NOT treated as transient", not isinstance(raised, client_mod.HomGarTransientError),
          f"got {type(raised).__name__}")
    check("a 404 is not retried (1 GET)", _count(session, _LIST) == 1, str(session.calls))
    check("a 404 does not sleep", len(_SLEEPS) == 0, f"sleeps={_SLEEPS}")


async def _test_clean_200_never_retries():
    _SLEEPS.clear()
    script = {_LIST: [(200, {"code": 0, "data": [{"hid": 7}]})]}
    client, session = _make_client(script)
    result = await client.list_homes()
    check("clean 200 returns immediately", result == [{"hid": 7}], f"got {result!r}")
    check("clean 200 issues a single GET", _count(session, _LIST) == 1, str(session.calls))
    check("clean 200 never sleeps", len(_SLEEPS) == 0, f"sleeps={_SLEEPS}")


async def _test_control_command_does_not_retry_on_transient():
    # An irrigation command ("start for N seconds") is absolute, not idempotent.
    # A post-send disconnect/timeout must NOT trigger an automatic resend, which
    # could restart/extend watering. Control endpoints fail fast instead.
    _SLEEPS.clear()
    _CTL = "/app/device/controlWorkMode"
    script = {_CTL: [asyncio.TimeoutError("Connection timeout to host"), (200, {"code": 0, "data": {}})]}
    client, session = _make_client(script)
    raised = None
    try:
        await client.control_work_mode(
            mid=1, addr=2, device_name="d", product_key="p", port=1, mode=1, duration=60,
        )
    except client_mod.HomGarApiError as err:
        raised = err
    check("control_work_mode does NOT retry a transient error", _count(session, _CTL) == 1, str(session.calls))
    check("control_work_mode surfaces the transient failure", raised is not None)
    check("control_work_mode did not sleep/backoff on a write", len(_SLEEPS) == 0, f"sleeps={_SLEEPS}")


async def _test_set_device_state_does_not_retry_on_5xx():
    _SLEEPS.clear()
    _SET = "/app/device/setDeviceStatus"
    script = {_SET: [(503, {}), (200, {"code": 0})]}
    client, session = _make_client(script)
    raised = None
    try:
        await client.set_device_state(
            home_id=1, device_name="d", mid=1, product_key="p", state={"port_1": True},
        )
    except client_mod.HomGarApiError as err:
        raised = err
    check("set_device_state does NOT retry a 503 write", _count(session, _SET) == 1, str(session.calls))
    check("set_device_state raises on the 503", raised is not None)


def _test_backoff_constant_sane():
    b = client_mod._TRANSIENT_RETRY_BACKOFF
    check("backoff schedule is a non-empty tuple", isinstance(b, tuple) and len(b) >= 1, f"got {b!r}")
    check("total backoff stays within a single poll (<30s)", sum(b) < 30, f"sum={sum(b)}")
    check("HomGarTransientError subclasses HomGarApiError",
          issubclass(client_mod.HomGarTransientError, client_mod.HomGarApiError))


def main() -> int:
    print("Transient-error retry/backoff regression tests (issue #82)")
    _test_backoff_constant_sane()
    original_sleep = client_mod.asyncio.sleep
    client_mod.asyncio.sleep = _fake_sleep
    try:
        asyncio.run(_test_retries_503_then_succeeds())
        asyncio.run(_test_retries_connection_error_then_succeeds())
        asyncio.run(_test_retries_timeout_then_succeeds())
        asyncio.run(_test_exhausts_retries_then_raises_transient())
        asyncio.run(_test_4xx_raises_immediately_without_retry())
        asyncio.run(_test_clean_200_never_retries())
        asyncio.run(_test_control_command_does_not_retry_on_transient())
        asyncio.run(_test_set_device_state_does_not_retry_on_5xx())
    finally:
        client_mod.asyncio.sleep = original_sleep
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
