"""Regression tests: HomGarClient exposes token re-auth telemetry.

The three diagnostic sensors (added in v3.0.41) read this state. We pin that
_reauth() increments a session counter and records when/what triggered it, and
that the read-only accessors reflect it. See the token-reauth diagnostic spec.
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


class _ClientTimeout:
    def __init__(self, total=None, connect=None, sock_connect=None, sock_read=None):
        self.total = total


_aiohttp_stub = types.ModuleType("aiohttp")
_aiohttp_stub.ClientTimeout = _ClientTimeout
_aiohttp_stub.ClientSession = type("ClientSession", (), {})
_aiohttp_stub.ClientError = type("ClientError", (Exception,), {})
sys.modules["aiohttp"] = _aiohttp_stub

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
    "code": 0, "ts": 1700000000000,
    "data": {"token": "fresh", "refreshToken": "r", "tokenExpired": 3600, "user": {}},
}


class _SequencedSession:
    def __init__(self, queues):
        self._queues = {u: list(p) for u, p in queues.items()}
        self.login_posts = 0

    def _next(self, url):
        if url.endswith("/auth/basic/app/login"):
            self.login_posts += 1
            return _FakeResp(_LOGIN_PAYLOAD)
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
    client._token = "stale"
    client._refresh_token = "stale-r"
    client._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return client


def _test_initial_state():
    client = _make_client({})
    check("reauth_count starts at 0", client.reauth_count == 0, f"got {client.reauth_count}")
    check("last_reauth_at starts None", client.last_reauth_at is None)
    check("last_reauth_trigger starts None", client.last_reauth_trigger is None)
    check("last_reauth_code starts None", client.last_reauth_code is None)
    check("token_expires_at accessor works", client.token_expires_at is not None)


async def _test_reauth_records_telemetry():
    # subscribe_status hits 1001 then recovers -> one reauth recorded.
    ok = {"code": 0, "data": {"deviceName": "x"}}
    client = _make_client({"/app/device/subscribeStatus": [{"code": 1001, "msg": "NOT_TOKEN"}, ok]})
    await client.subscribe_status(hid=1, hubs=[{"deviceName": "d", "mid": 1, "productKey": "p", "hid": 1}])
    check("reauth_count == 1 after one rejection", client.reauth_count == 1, f"got {client.reauth_count}")
    check("last_reauth_at is set", client.last_reauth_at is not None)
    check("trigger recorded as subscribeStatus", client.last_reauth_trigger == "subscribeStatus",
          f"got {client.last_reauth_trigger!r}")
    check("code recorded as 1001", client.last_reauth_code == 1001, f"got {client.last_reauth_code}")


async def _test_reauth_count_is_monotonic():
    client = _make_client({})
    await client._reauth(trigger="controlWorkMode", code=1004)
    await client._reauth(trigger="getDeviceStatus", code=1004)
    check("reauth_count increments to 2", client.reauth_count == 2, f"got {client.reauth_count}")
    check("latest trigger wins", client.last_reauth_trigger == "getDeviceStatus",
          f"got {client.last_reauth_trigger!r}")


async def _test_concurrent_reauth_single_login():
    # Two callers whose in-flight requests used the same (now-rejected) token both
    # trigger a re-auth in the same window. The auth lock must collapse them into
    # ONE login instead of a re-login storm.
    client = _make_client({})
    used = client._token  # both in-flight requests used this (now-rejected) token
    await asyncio.gather(
        client._reauth(trigger="multipleDeviceStatus", code=1001, rejected_token=used),
        client._reauth(trigger="subscribeStatus", code=1001, rejected_token=used),
    )
    check("concurrent re-auth performs exactly one login",
          client._session.login_posts == 1, f"got {client._session.login_posts}")
    check("concurrent re-auth counted once (no double increment)",
          client.reauth_count == 1, f"got {client.reauth_count}")


async def _test_single_reauth_still_logs_in():
    # A lone re-auth (no concurrent refresher) must still perform its login.
    client = _make_client({})
    await client._reauth(trigger="controlWorkMode", code=1004)
    check("single re-auth performs one login", client._session.login_posts == 1,
          f"got {client._session.login_posts}")
    check("single re-auth counted once", client.reauth_count == 1, f"got {client.reauth_count}")


def main() -> int:
    print("Token diagnostic telemetry tests")
    _test_initial_state()
    asyncio.run(_test_reauth_records_telemetry())
    asyncio.run(_test_reauth_count_is_monotonic())
    asyncio.run(_test_concurrent_reauth_single_login())
    asyncio.run(_test_single_reauth_still_logs_in())
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
