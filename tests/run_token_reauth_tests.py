"""Regression tests: valve control endpoints re-auth and retry on a token error.

The HomGar cloud returns ``code=1004 "token error"`` when it rejects a token
(rotation, or a local expiry clock that outlives the server-side token). The
read endpoints (``list_homes`` etc.) already recover from this by calling
``_reauth()`` and retrying once. The control endpoints (``control_work_mode`` /
``control_work_mode_dp``) historically did NOT — a stale token turned a valve
command into a hard ``HomGarApiError`` (reported following the User-Agent 403
fix in #75/#76/#77, which first let control calls reach the cloud at all).

These tests pin the recovery behaviour: a 1004 on a control call triggers a
single fresh login and a retry, and a clean 0 response never re-auths.
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
        self.sock_connect = sock_connect
        self.sock_read = sock_read


class _ClientSession:  # only needed for the type annotation in __init__
    pass


_aiohttp_stub = types.ModuleType("aiohttp")
_aiohttp_stub.ClientTimeout = _ClientTimeout
_aiohttp_stub.ClientSession = _ClientSession
_aiohttp_stub.ClientError = type("ClientError", (Exception,), {})
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


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return ""


_LOGIN_PAYLOAD = {
    "code": 0,
    "ts": 1700000000000,
    "data": {"token": "fresh-token", "refreshToken": "r", "tokenExpired": 3600, "user": {}},
}


class _SequencedSession:
    """Returns login success for the login URL and a queue of payloads per URL.

    Records the number of login POSTs so tests can assert whether a re-auth
    happened.
    """

    def __init__(self, queues: dict[str, list]):
        self._queues = {url: list(payloads) for url, payloads in queues.items()}
        self.login_posts = 0
        self.control_posts = 0

    def _next(self, url):
        if url.endswith("/auth/basic/app/login"):
            self.login_posts += 1
            return _FakeResp(_LOGIN_PAYLOAD)
        self.control_posts += 1
        for key, queue in self._queues.items():
            if url.endswith(key) and queue:
                return _FakeResp(queue.pop(0))
        raise AssertionError(f"No queued response for {url}")

    def post(self, url, **kwargs):
        return self._next(url)

    def get(self, url, **kwargs):
        return self._next(url)


def _make_client(queues):
    session = _SequencedSession(queues)
    client = client_mod.HomGarClient("31", "a@b.com", "pw", session, "homgar")
    # Pretend we already have a (soon-to-be-rejected) token whose LOCAL clock is
    # still valid, so ensure_logged_in() does not log in first — the stale token
    # goes out and the server answers 1004.
    client._token = "stale-token"
    client._refresh_token = "stale-refresh"
    client._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return client, session


_TOKEN_ERROR = {"code": 1004, "msg": "token error"}
_NOT_TOKEN = {"code": 1001, "msg": "NOT_TOKEN", "ts": 1784873946096}
_OK = {"code": 0, "data": {"state": "open"}}


async def _test_control_work_mode_reauths_on_1004():
    client, session = _make_client({"/app/device/controlWorkMode": [_TOKEN_ERROR, _OK]})
    result = await client.control_work_mode(
        mid=1, addr=2, device_name="d", product_key="p", port=1, mode=1, duration=60,
    )
    check(
        "control_work_mode recovers from 1004 (no exception)",
        result == "open",
        f"got {result!r}",
    )
    check(
        "control_work_mode performed exactly one re-login",
        session.login_posts == 1,
        f"login_posts={session.login_posts}",
    )
    check(
        "control_work_mode retried the control call once (2 control POSTs)",
        session.control_posts == 2,
        f"control_posts={session.control_posts}",
    )


async def _test_control_work_mode_dp_reauths_on_1004():
    client, session = _make_client({"/app/device/controlWorkModeDP": [_TOKEN_ERROR, _OK]})
    result = await client.control_work_mode_dp(
        mid=1, addr=2, device_name="d", product_key="p", port=1, mode=1, duration=60, hid=99,
    )
    check(
        "control_work_mode_dp recovers from 1004 (no exception)",
        result == "open",
        f"got {result!r}",
    )
    check(
        "control_work_mode_dp performed exactly one re-login",
        session.login_posts == 1,
        f"login_posts={session.login_posts}",
    )
    check(
        "control_work_mode_dp retried the control call once (2 control POSTs)",
        session.control_posts == 2,
        f"control_posts={session.control_posts}",
    )


async def _test_control_work_mode_no_reauth_on_success():
    client, session = _make_client({"/app/device/controlWorkMode": [_OK]})
    result = await client.control_work_mode(
        mid=1, addr=2, device_name="d", product_key="p", port=1, mode=1, duration=60,
    )
    check("control_work_mode returns state on clean success", result == "open", f"got {result!r}")
    check(
        "control_work_mode does NOT re-login on a clean 0 response",
        session.login_posts == 0,
        f"login_posts={session.login_posts}",
    )
    check(
        "control_work_mode issues a single control POST on success",
        session.control_posts == 1,
        f"control_posts={session.control_posts}",
    )


async def _test_control_work_mode_still_raises_on_other_error():
    client, session = _make_client({"/app/device/controlWorkMode": [{"code": 99, "msg": "boom"}]})
    raised = False
    try:
        await client.control_work_mode(
            mid=1, addr=2, device_name="d", product_key="p", port=1, mode=1, duration=60,
        )
    except client_mod.HomGarApiError:
        raised = True
    check("control_work_mode still raises on a non-token error (code 99)", raised)
    check(
        "control_work_mode does not re-login on a non-token error",
        session.login_posts == 0,
        f"login_posts={session.login_posts}",
    )


async def _test_subscribe_status_reauths_on_1001():
    """Shaun's exact MQTT-renewal failure: subscribeStatus -> code 1001 NOT_TOKEN."""
    ok_payload = {"code": 0, "data": {"deviceName": "x", "productKey": "p"}}
    client, session = _make_client({"/app/device/subscribeStatus": [_NOT_TOKEN, ok_payload]})
    result = await client.subscribe_status(
        hid=1, hubs=[{"deviceName": "d", "mid": 1, "productKey": "p", "hid": 1}],
    )
    check(
        "subscribe_status recovers from 1001 NOT_TOKEN (no exception)",
        result == {"deviceName": "x", "productKey": "p"},
        f"got {result!r}",
    )
    check(
        "subscribe_status performed exactly one re-login",
        session.login_posts == 1,
        f"login_posts={session.login_posts}",
    )
    check(
        "subscribe_status retried once (2 subscribeStatus POSTs)",
        session.control_posts == 2,
        f"control_posts={session.control_posts}",
    )


async def _test_get_device_status_reauths_on_1004():
    ok_payload = {"code": 0, "data": {"battery": 100}}
    client, session = _make_client({"/app/device/getDeviceStatus": [_TOKEN_ERROR, ok_payload]})
    result = await client.get_device_status(mid=1)
    check(
        "get_device_status recovers from 1004 (no exception)",
        result == {"battery": 100},
        f"got {result!r}",
    )
    check("get_device_status re-logged in once", session.login_posts == 1, f"login_posts={session.login_posts}")
    check("get_device_status retried once", session.control_posts == 2, f"control_posts={session.control_posts}")


async def _test_set_device_state_reauths_on_1004():
    client, session = _make_client({"/app/device/setDeviceStatus": [_TOKEN_ERROR, {"code": 0}]})
    result = await client.set_device_state(
        home_id=1, device_name="d", mid=1, product_key="p", state={"port_1": True},
    )
    check("set_device_state recovers from 1004 (returns True)", result is True, f"got {result!r}")
    check("set_device_state re-logged in once", session.login_posts == 1, f"login_posts={session.login_posts}")
    check("set_device_state retried once", session.control_posts == 2, f"control_posts={session.control_posts}")


async def _test_get_product_models_reauths_on_1004():
    ok_payload = {"code": 0, "data": {"models": [{"id": 1}, {"id": 2}]}}
    client, session = _make_client({"/app/common/core/productModel": [_TOKEN_ERROR, ok_payload]})
    result = await client.get_product_models()
    check(
        "get_product_models recovers from 1004 (returns models, not [])",
        result == [{"id": 1}, {"id": 2}],
        f"got {result!r}",
    )
    check("get_product_models re-logged in once", session.login_posts == 1, f"login_posts={session.login_posts}")
    check("get_product_models retried once", session.control_posts == 2, f"control_posts={session.control_posts}")


def main() -> int:
    print("Token re-auth / retry regression tests")
    asyncio.run(_test_control_work_mode_reauths_on_1004())
    asyncio.run(_test_control_work_mode_dp_reauths_on_1004())
    asyncio.run(_test_control_work_mode_no_reauth_on_success())
    asyncio.run(_test_control_work_mode_still_raises_on_other_error())
    asyncio.run(_test_subscribe_status_reauths_on_1001())
    asyncio.run(_test_get_device_status_reauths_on_1004())
    asyncio.run(_test_set_device_state_reauths_on_1004())
    asyncio.run(_test_get_product_models_reauths_on_1004())
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
