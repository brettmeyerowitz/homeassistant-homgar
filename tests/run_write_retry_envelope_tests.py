"""Regression tests: the write retry ENVELOPE and write-failure visibility.

Issue #82, second field report (2026-08-22). A reporter ran an independent
per-minute curl probe from a separate machine on the same LAN as HA, against
region3.homgarus.com, and caught a failure window:

    07:00:20  OK      tcp=0.173s  tls=1.236s  code=200
    07:01:21  FAILED  SSL connection timeout
    07:02:36  OK      tcp=0.175s  tls=3.657s  code=200
    07:03:40  FAILED  SSL connection timeout
    07:04:55  OK      tcp=0.178s  tls=4.536s  code=200
    07:06:00  FAILED  SSL connection timeout
    07:07:15  OK      tcp=0.168s  tls=2.032s  code=200

Two facts drive everything here.

**The brownouts last minutes, not milliseconds.** The previous policy gave a
write exactly one resend one second later, which lands squarely inside the same
degraded window. Reads, meanwhile, got three retries AND self-heal on the next
120s poll. That asymmetry was backwards: a missed valve command has no next
poll, so the operation that cannot recover on its own had the shortest retry
envelope in the codebase. These tests pin the widened envelope.

**Only the TLS handshake degraded; TCP connect stayed flat at 0.167-0.187s.**
aiohttp's sock_connect budget covers the handshake, not just the TCP connect
(TCPConnector._wrap_create_connection runs loop.create_connection inside
ceil_timeout(sock_connect)), and anything timing out inside connector.connect()
surfaces as ConnectionTimeoutError. The slowest *successful* handshake observed
was 4.5s against a 10s budget - barely any headroom - so the budget is raised.
It is raised WITHIN the unchanged 30s total, so the worst-case duration of a
single attempt does not grow.

Widening the envelope is safe by construction: every delay here is applied only
to provably pre-send failures, where no request byte was ever transmitted, so a
resend cannot double-actuate irrigation no matter how long we wait. The
narrow-classifier guarantee is pinned by run_write_presend_retry_tests.py; this
suite assumes it and tests what happens *after* classification.

Also covered: jitter (thousands of installs must not retry in lockstep against a
single origin with no CDN), the wall-clock deadline that bounds how long a
service call may block, and the write-failure telemetry + callback that stop a
dead valve command from being silent. Stdlib only.
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


# --- constants: the envelope itself -----------------------------------------


def _test_envelope_constants():
    b = client_mod._WRITE_PRE_SEND_RETRY_BACKOFF
    check("write envelope is wider than a single 1s resend", len(b) > 1, f"got {b!r}")
    check("write backoff is non-decreasing", list(b) == sorted(b), f"got {b!r}")
    check("write envelope spans tens of seconds (last step >= 15s)",
          b[-1] >= 15, f"got {b!r}")
    check("write envelope still starts small (first step <= 5s)",
          b[0] <= 5, f"got {b!r}")

    j = client_mod._WRITE_PRE_SEND_JITTER
    check("jitter fraction is a real spread", 0 < j < 1, f"got {j!r}")

    d = client_mod._WRITE_PRE_SEND_DEADLINE
    check("a wall-clock deadline bounds how long a service call may block",
          0 < d <= 120, f"got {d!r}")
    check("deadline is large enough to contain the nominal backoff",
          d >= sum(b), f"deadline={d} sum(backoff)={sum(b)}")

    # Reads must be untouched: they already self-heal on the next poll, and
    # lengthening them would push a failing poll past the 120s interval.
    check("read backoff is unchanged", tuple(client_mod._TRANSIENT_RETRY_BACKOFF) == (1, 2, 4),
          f"got {client_mod._TRANSIENT_RETRY_BACKOFF!r}")


def _test_handshake_budget():
    t = client_mod._REQUEST_TIMEOUT
    check("handshake budget raised above the observed 4.5s worst success",
          t.connect >= 15, f"connect={t.connect}")
    check("per-attempt worst case is NOT lengthened (total unchanged at 30s)",
          t.total == 30, f"total={t.total}")
    check("handshake budget stays inside the total", t.connect <= t.total,
          f"connect={t.connect} total={t.total}")


# --- jitter -----------------------------------------------------------------


def _test_jitter_spreads_delays():
    j = client_mod._WRITE_PRE_SEND_JITTER
    base = 8.0
    samples = [client_mod._jittered(base) for _ in range(200)]
    check("jitter stays within its declared spread",
          all(base * (1 - j) - 1e-9 <= s <= base * (1 + j) + 1e-9 for s in samples),
          f"min={min(samples)} max={max(samples)}")
    check("jitter actually varies (not a constant)", len(set(samples)) > 100,
          f"distinct={len(set(samples))}")
    check("jitter is centred near the base delay",
          abs(sum(samples) / len(samples) - base) < base * j,
          f"mean={sum(samples)/len(samples)}")
    check("jitter never returns a negative delay", min(samples) >= 0)


# --- the write path end to end ----------------------------------------------


async def _test_write_uses_full_envelope():
    """A pre-send failure that never clears must exhaust the whole envelope."""
    _SLEEPS.clear()
    b = client_mod._WRITE_PRE_SEND_RETRY_BACKOFF
    err = aiohttp.ConnectionTimeoutError("Connection timeout to host https://x")
    script = {_CTL: [err] * (len(b) + 1)}
    client, session = _make_client(script)
    raised = None
    try:
        await _open_valve(client)
    except client_mod.HomGarApiError as e:
        raised = e
    check("exhausted write still raises", isinstance(raised, client_mod.HomGarTransientError),
          f"raised {raised!r}")
    check(f"it made {len(b) + 1} attempts", _count(session, _CTL) == len(b) + 1,
          f"made {_count(session, _CTL)}")
    check("it slept between every attempt", len(_SLEEPS) == len(b), f"sleeps={_SLEEPS}")
    j = client_mod._WRITE_PRE_SEND_JITTER
    check("each sleep is a jittered form of its base delay",
          all(base * (1 - j) - 1e-9 <= s <= base * (1 + j) + 1e-9
              for base, s in zip(b, _SLEEPS)),
          f"backoff={b} sleeps={_SLEEPS}")
    check("total wait spans tens of seconds, not one",
          sum(_SLEEPS) > 15, f"sum={sum(_SLEEPS)}")


async def _test_write_recovers_mid_envelope():
    """The realistic case: the brownout clears partway through the envelope."""
    _SLEEPS.clear()
    err = aiohttp.ConnectionTimeoutError("Connection timeout to host https://x")
    script = {_CTL: [err, err, (200, {"code": 0, "data": {}})]}
    client, session = _make_client(script)
    raised = None
    try:
        await _open_valve(client)
    except client_mod.HomGarApiError as e:
        raised = e
    check("valve command succeeds on the third attempt", raised is None, f"raised {raised!r}")
    check("it stopped as soon as it succeeded", _count(session, _CTL) == 3,
          str(session.calls))


async def _test_deadline_truncates_envelope():
    """The deadline is what stops a service call blocking an automation for
    minutes. Simulate a slow cloud by advancing the clock inside the fake sleep."""
    _SLEEPS.clear()
    err = aiohttp.ConnectionTimeoutError("Connection timeout to host https://x")
    b = client_mod._WRITE_PRE_SEND_RETRY_BACKOFF
    script = {_CTL: [err] * (len(b) + 1)}
    client, session = _make_client(script)

    # Burn the deadline on the very first attempt.
    clock = {"t": 0.0}
    original_monotonic = client_mod.time.monotonic
    client_mod.time.monotonic = lambda: clock["t"]
    clock["t"] = 0.0

    async def _slow_sleep(delay):
        _SLEEPS.append(delay)
        clock["t"] += client_mod._WRITE_PRE_SEND_DEADLINE  # blow the budget

    original_sleep = client_mod.asyncio.sleep
    client_mod.asyncio.sleep = _slow_sleep
    try:
        raised = None
        try:
            await _open_valve(client)
        except client_mod.HomGarApiError as e:
            raised = e
    finally:
        client_mod.asyncio.sleep = original_sleep
        client_mod.time.monotonic = original_monotonic

    check("deadline still surfaces the failure", raised is not None)
    check("deadline cut the envelope short", _count(session, _CTL) < len(b) + 1,
          f"made {_count(session, _CTL)} of {len(b) + 1}")
    check("deadline did not stop it retrying at all", _count(session, _CTL) >= 2,
          f"made {_count(session, _CTL)}")


async def _test_ambiguous_write_failure_still_fails_fast():
    """The no-double-actuation guarantee must survive the widened envelope."""
    _SLEEPS.clear()
    err = aiohttp.SocketTimeoutError("Timeout on reading data")
    script = {_CTL: [err, (200, {"code": 0, "data": {}})]}
    client, session = _make_client(script)
    raised = None
    try:
        await _open_valve(client)
    except client_mod.HomGarApiError as e:
        raised = e
    check("a read timeout on a write is NOT retried", _count(session, _CTL) == 1,
          str(session.calls))
    check("it did not sleep", len(_SLEEPS) == 0, f"sleeps={_SLEEPS}")
    check("it raised", raised is not None)


async def _test_reads_keep_their_own_backoff():
    """Reads must not inherit the write envelope: a failing poll has to finish
    well inside the 120s coordinator interval."""
    _SLEEPS.clear()
    _PROBE = "/app/device/probe"
    err = aiohttp.ConnectionTimeoutError("Connection timeout to host https://x")
    client, session = _make_client({_PROBE: [err] * 4})
    try:
        await client._request_json("get", f"https://x{_PROBE}", what="probe", retry=True)
    except client_mod.HomGarApiError:
        pass
    check("read backoff is still exactly (1, 2, 4)",
          _SLEEPS == list(client_mod._TRANSIENT_RETRY_BACKOFF), f"sleeps={_SLEEPS}")
    check("read retries are not jittered (deterministic poll budget)",
          all(float(s).is_integer() for s in _SLEEPS), f"sleeps={_SLEEPS}")


# --- a failed command must not be silent ------------------------------------


async def _test_write_failure_is_recorded():
    _SLEEPS.clear()
    err = aiohttp.ConnectionTimeoutError("Connection timeout to host https://x")
    b = client_mod._WRITE_PRE_SEND_RETRY_BACKOFF
    client, _session = _make_client({_CTL: [err] * (len(b) + 1)})
    check("write failure count starts at zero", client.write_failure_count == 0)
    check("no last write failure yet", client.last_write_failure_at is None)
    try:
        await _open_valve(client)
    except client_mod.HomGarApiError:
        pass
    check("write failure was counted", client.write_failure_count == 1,
          f"got {client.write_failure_count}")
    check("the failing endpoint was recorded",
          client.last_write_failure_what == "controlWorkMode",
          f"got {client.last_write_failure_what!r}")
    check("a timestamp was recorded", client.last_write_failure_at is not None)
    check("the error text was recorded",
          "controlWorkMode" in (client.last_write_failure_error or ""),
          f"got {client.last_write_failure_error!r}")


async def _test_read_failure_is_not_recorded_as_a_write():
    """Polling recovers by itself; counting it here would bury the signal."""
    _SLEEPS.clear()
    err = aiohttp.ConnectionTimeoutError("Connection timeout to host https://x")
    _PROBE = "/app/device/probe"
    client, _session = _make_client({_PROBE: [err] * 4})
    try:
        await client._request_json("get", f"https://x{_PROBE}", what="probe", retry=True)
    except client_mod.HomGarApiError:
        pass
    check("a failed poll is NOT counted as a write failure",
          client.write_failure_count == 0, f"got {client.write_failure_count}")


async def _test_write_failure_callback():
    _SLEEPS.clear()
    seen = []
    err = aiohttp.ConnectionTimeoutError("Connection timeout to host https://x")
    b = client_mod._WRITE_PRE_SEND_RETRY_BACKOFF
    client, _session = _make_client({_CTL: [err] * (len(b) + 1)})
    client.on_write_failure = lambda what, detail: seen.append((what, detail))
    try:
        await _open_valve(client)
    except client_mod.HomGarApiError:
        pass
    check("the callback fired exactly once", len(seen) == 1, f"got {seen!r}")
    check("the callback was told which command failed",
          seen and seen[0][0] == "controlWorkMode", f"got {seen!r}")


async def _test_callback_failure_never_breaks_the_command():
    """Defense in depth: notification plumbing must not turn a cloud failure
    into a different, more confusing traceback."""
    _SLEEPS.clear()
    err = aiohttp.ConnectionTimeoutError("Connection timeout to host https://x")
    b = client_mod._WRITE_PRE_SEND_RETRY_BACKOFF
    client, _session = _make_client({_CTL: [err] * (len(b) + 1)})

    def _boom(what, detail):
        raise RuntimeError("notification backend exploded")

    client.on_write_failure = _boom
    raised = None
    try:
        await _open_valve(client)
    except BaseException as e:
        raised = e
    check("the original transient error still surfaces",
          isinstance(raised, client_mod.HomGarTransientError), f"raised {raised!r}")


async def _test_non_transient_write_failure_also_recorded():
    """A 4xx write is just as silent to the user as a timeout was."""
    _SLEEPS.clear()
    client, _session = _make_client({_CTL: [(403, {})]})
    try:
        await _open_valve(client)
    except client_mod.HomGarApiError:
        pass
    check("a 4xx write failure is recorded too", client.write_failure_count == 1,
          f"got {client.write_failure_count}")


def main() -> int:
    print("Write retry envelope + failure visibility tests (issue #82, 2026-08-22)")
    _test_envelope_constants()
    _test_handshake_budget()
    _test_jitter_spreads_delays()
    original_sleep = client_mod.asyncio.sleep
    client_mod.asyncio.sleep = _fake_sleep
    try:
        asyncio.run(_test_write_uses_full_envelope())
        asyncio.run(_test_write_recovers_mid_envelope())
        asyncio.run(_test_ambiguous_write_failure_still_fails_fast())
        asyncio.run(_test_reads_keep_their_own_backoff())
        asyncio.run(_test_write_failure_is_recorded())
        asyncio.run(_test_read_failure_is_not_recorded_as_a_write())
        asyncio.run(_test_write_failure_callback())
        asyncio.run(_test_callback_failure_never_breaks_the_command())
        asyncio.run(_test_non_transient_write_failure_also_recorded())
    finally:
        client_mod.asyncio.sleep = original_sleep
    asyncio.run(_test_deadline_truncates_envelope())
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
