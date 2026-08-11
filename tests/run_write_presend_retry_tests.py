"""Regression tests: write/control commands retry ONLY provably pre-send failures.

Issue #82 follow-up. Write endpoints (controlWorkMode, controlWorkModeDP,
setDeviceStatus) are absolute, not idempotent — "run for N seconds" resent after
the cloud already accepted it can re-actuate irrigation — so they were given a
blanket ``retry=False``. A live report on 2026-08-10 showed the cost: opening a
valve failed outright with

    controlWorkMode: Connection timeout to host .../app/device/controlWorkMode

and an immediate manual retry succeeded.

That particular failure did not need to fail. aiohttp raises it from
``_connect_and_send_request`` when ``connector.connect()`` times out — before any
request bytes leave the client — so the cloud provably never saw the command and
a resend cannot double-actuate. The same holds for DNS/refused connect errors.

So writes now retry exactly the connect-phase failures and nothing else. The
distinction is subtle in aiohttp's hierarchy and easy to get wrong:

  * ClientConnectorError subclasses ClientOSError, so a broad ClientOSError
    check would wrongly admit mid-flight socket errors.
  * ConnectionTimeoutError AND SocketTimeoutError both subclass
    ServerTimeoutError, so a broad ServerTimeoutError check would wrongly admit
    read timeouts, which happen after the request was sent.

These tests pin both traps. Reads are unaffected — they already retry everything
transient. Runs on the host and in the ha-test container, stdlib only.
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


# --- aiohttp stub mirroring the real exception hierarchy --------------------
# The MROs below are copied from aiohttp 3.13; the subclass relationships are
# the whole point of these tests, so they must not be simplified.


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
# ClientOSError -> ClientConnectionError; ClientConnectorError -> ClientOSError.
_aiohttp_stub.ClientOSError = type(
    "ClientOSError", (_aiohttp_stub.ClientConnectionError, OSError), {})
_aiohttp_stub.ClientConnectorError = type(
    "ClientConnectorError", (_aiohttp_stub.ClientOSError,), {})
# ServerConnectionError -> ClientConnectionError; both timeout flavours subclass
# ServerTimeoutError, which also subclasses asyncio.TimeoutError.
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
    def __init__(self, action):
        self._action = action

    async def __aenter__(self):
        if isinstance(self._action, BaseException):
            raise self._action
        status, payload = self._action
        return _FakeResp(status, payload)

    async def __aexit__(self, *exc):
        return False


class _ScriptedSession:
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


_CTL = "/app/device/controlWorkMode"
_SET = "/app/device/setDeviceStatus"
_SLEEPS: list[float] = []


async def _fake_sleep(delay):
    _SLEEPS.append(delay)


async def _open_valve(client):
    return await client.control_work_mode(
        mid=1, addr=2, device_name="d", product_key="p", port=1, mode=1, duration=60,
    )


# --- the classifier itself --------------------------------------------------


def _test_classifier():
    f = client_mod._is_pre_send_error
    check("connect timeout is pre-send",
          f(aiohttp.ConnectionTimeoutError("Connection timeout to host https://x")) is True)
    check("connector/DNS error is pre-send",
          f(aiohttp.ClientConnectorError("Cannot connect to host x:443")) is True)

    # The two traps this design is most likely to regress into.
    check("read timeout is NOT pre-send (subclasses ServerTimeoutError)",
          f(aiohttp.SocketTimeoutError("Timeout on reading data")) is False)
    check("mid-flight ClientOSError is NOT pre-send (ClientConnectorError's base)",
          f(aiohttp.ClientOSError("Connection reset by peer")) is False)

    check("server disconnect is NOT pre-send",
          f(aiohttp.ServerDisconnectedError("Server disconnected")) is False)
    check("bare asyncio.TimeoutError is NOT pre-send (ambiguous)",
          f(asyncio.TimeoutError("Connection timeout to host")) is False)
    check("a 5xx-derived transient error is NOT pre-send",
          f(client_mod.HomGarTransientError("controlWorkMode HTTP 503")) is False)


# --- write path -------------------------------------------------------------


async def _test_write_retries_connect_timeout():
    """The reported failure: the command never reached the cloud, so resending
    it cannot double-actuate."""
    _SLEEPS.clear()
    err = aiohttp.ConnectionTimeoutError(f"Connection timeout to host https://x{_CTL}")
    script = {_CTL: [err, (200, {"code": 0, "data": {}})]}
    client, session = _make_client(script)
    raised = None
    try:
        # Returns an optional state string; None is a valid success here, so the
        # assertion is that it did not raise.
        await _open_valve(client)
    except client_mod.HomGarApiError as e:
        raised = e
    check("valve command succeeds after a connect timeout", raised is None, f"raised {raised!r}")
    check("it retried exactly once (2 POSTs)", _count(session, _CTL) == 2, str(session.calls))
    check("it backed off once before resending", len(_SLEEPS) == 1, f"sleeps={_SLEEPS}")


async def _test_write_retries_connector_error():
    _SLEEPS.clear()
    err = aiohttp.ClientConnectorError("Cannot connect to host region3.homgarus.com:443")
    script = {_CTL: [err, (200, {"code": 0, "data": {}})]}
    client, session = _make_client(script)
    await _open_valve(client)
    check("valve command succeeds after a DNS/connect error", _count(session, _CTL) == 2, str(session.calls))


async def _test_write_does_not_retry_read_timeout():
    """Post-send: the cloud may already be watering. Must fail fast."""
    _SLEEPS.clear()
    err = aiohttp.SocketTimeoutError("Timeout on reading data from socket")
    script = {_CTL: [err, (200, {"code": 0, "data": {}})]}
    client, session = _make_client(script)
    raised = None
    try:
        await _open_valve(client)
    except client_mod.HomGarApiError as e:
        raised = e
    check("read timeout on a write is NOT retried", _count(session, _CTL) == 1, str(session.calls))
    check("read timeout surfaces to the caller", raised is not None)
    check("no backoff slept on a non-retried write", len(_SLEEPS) == 0, f"sleeps={_SLEEPS}")


async def _test_write_does_not_retry_disconnect():
    _SLEEPS.clear()
    err = aiohttp.ServerDisconnectedError("Server disconnected")
    script = {_CTL: [err, (200, {"code": 0, "data": {}})]}
    client, session = _make_client(script)
    try:
        await _open_valve(client)
    except client_mod.HomGarApiError:
        pass
    check("server disconnect on a write is NOT retried", _count(session, _CTL) == 1, str(session.calls))


async def _test_write_does_not_retry_5xx():
    """A 503 means the request was delivered and the server answered."""
    _SLEEPS.clear()
    script = {_SET: [(503, {}), (200, {"code": 0})]}
    client, session = _make_client(script)
    raised = None
    try:
        await client.set_device_state(
            home_id=1, device_name="d", mid=1, product_key="p", state={"port_1": True},
        )
    except client_mod.HomGarApiError as e:
        raised = e
    check("503 on a write is NOT retried", _count(session, _SET) == 1, str(session.calls))
    check("503 on a write raises", raised is not None)


async def _test_write_gives_up_after_one_retry():
    """Bounded: a user is waiting on a button press, so one resend only."""
    _SLEEPS.clear()
    err = aiohttp.ConnectionTimeoutError("Connection timeout to host https://x")
    script = {_CTL: [err] * 10}
    client, session = _make_client(script)
    raised = None
    try:
        await _open_valve(client)
    except client_mod.HomGarApiError as e:
        raised = e
    check("a persistent connect timeout stops after 2 attempts",
          _count(session, _CTL) == 2, str(session.calls))
    check("it still raises HomGarTransientError",
          isinstance(raised, client_mod.HomGarTransientError), f"got {type(raised).__name__}")


def _test_backoff_constant_sane():
    b = client_mod._WRITE_PRE_SEND_RETRY_BACKOFF
    check("write backoff is a non-empty tuple", isinstance(b, tuple) and len(b) >= 1, f"got {b!r}")
    check("write retries at most once (a user is waiting)", len(b) == 1, f"got {b!r}")
    check("write backoff is short (<=2s)", sum(b) <= 2, f"sum={sum(b)}")


def main() -> int:
    print("Write-path pre-send retry tests (issue #82 follow-up)")
    _test_classifier()
    _test_backoff_constant_sane()
    original_sleep = client_mod.asyncio.sleep
    client_mod.asyncio.sleep = _fake_sleep
    try:
        asyncio.run(_test_write_retries_connect_timeout())
        asyncio.run(_test_write_retries_connector_error())
        asyncio.run(_test_write_does_not_retry_read_timeout())
        asyncio.run(_test_write_does_not_retry_disconnect())
        asyncio.run(_test_write_does_not_retry_5xx())
        asyncio.run(_test_write_gives_up_after_one_retry())
    finally:
        client_mod.asyncio.sleep = original_sleep
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
