"""Regression tests: every HomGar API request carries an explicit timeout.

Without an explicit ``aiohttp.ClientTimeout`` the requests inherit aiohttp's 300s
default total timeout, which lets a single stalled/poisoned connection wedge a
whole coordinator cycle for minutes during upstream flakiness. These tests pin
the behaviour that the client always passes ``_REQUEST_TIMEOUT``.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
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

# Register package scaffolding so client.py's ``from ..const import ...`` resolves.
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


class _RecordingSession:
    """Records the ``timeout`` kwarg passed to each get/post call."""

    def __init__(self, payload):
        self._payload = payload
        self.calls: list[tuple[str, str, object]] = []  # (method, url, timeout)

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs.get("timeout", "MISSING")))
        return _FakeResp(self._payload)

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs.get("timeout", "MISSING")))
        return _FakeResp(self._payload)


def _make_client(payload):
    session = _RecordingSession(payload)
    client = client_mod.HomGarClient("31", "a@b.com", "pw", session, "homgar")
    return client, session


async def _test_login_post_has_timeout():
    payload = {
        "code": 0,
        "ts": 1700000000000,
        "data": {"token": "tok", "refreshToken": "r", "tokenExpired": 3600, "user": {}},
    }
    client, session = _make_client(payload)
    ok = await client.login()
    check("login() succeeds against fake server", ok is True)
    login_calls = [c for c in session.calls if c[0] == "post"]
    check("login issues a POST", len(login_calls) == 1, str(session.calls))
    check(
        "login POST carries _REQUEST_TIMEOUT",
        login_calls and login_calls[0][2] is client_mod._REQUEST_TIMEOUT,
        f"got timeout={login_calls[0][2] if login_calls else None!r}",
    )


async def _test_get_path_has_timeout():
    payload = {"code": 0, "data": [], "ts": 1700000000000}
    client, session = _make_client(payload)
    # Pre-seed a valid token so ensure_logged_in() does not trigger a login POST.
    client._token = "tok"
    from datetime import datetime, timedelta, timezone

    client._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await client.list_homes()
    get_calls = [c for c in session.calls if c[0] == "get"]
    check("list_homes issues a GET", len(get_calls) == 1, str(session.calls))
    check(
        "list_homes GET carries _REQUEST_TIMEOUT",
        get_calls and get_calls[0][2] is client_mod._REQUEST_TIMEOUT,
        f"got timeout={get_calls[0][2] if get_calls else None!r}",
    )


def _test_timeout_values():
    t = client_mod._REQUEST_TIMEOUT
    check("timeout is an aiohttp.ClientTimeout", isinstance(t, _ClientTimeout))
    check("total timeout is bounded (<=60s)", t.total is not None and t.total <= 60, f"total={t.total}")
    check("connect timeout is set", t.connect is not None, f"connect={t.connect}")


def main() -> int:
    print("Request timeout regression tests")
    _test_timeout_values()
    asyncio.run(_test_login_post_has_timeout())
    asyncio.run(_test_get_path_has_timeout())
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
