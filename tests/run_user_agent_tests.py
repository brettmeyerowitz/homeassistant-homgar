"""Regression tests: every HomGar API request sends an app User-Agent.

As of ~mid-July 2026 the HomGar cloud (``region3.homgarus.com``, plain nginx)
returns ``403 Forbidden`` to any request whose ``User-Agent`` contains the
substring ``HomeAssistant``. HA's shared aiohttp session stamps
``HomeAssistant/<ver> aiohttp/<v> Python/<v>`` by default, so every call was
blocked. The client forces a neutral app-style UA in the ``_get``/``_post``
chokepoint. These tests pin that behaviour: the override is present on both
verbs, it wins over a caller/session-supplied header, it never contains
``HomeAssistant``, and it does not clobber other caller headers (e.g. ``auth``).
See issues #75 / #76 and PR #77.
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
    """Records the ``headers`` kwarg passed to each get/post call."""

    def __init__(self, payload):
        self._payload = payload
        self.calls: list[tuple[str, str, dict]] = []  # (method, url, headers)

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs.get("headers") or {}))
        return _FakeResp(self._payload)

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs.get("headers") or {}))
        return _FakeResp(self._payload)


def _make_client(payload):
    session = _RecordingSession(payload)
    client = client_mod.HomGarClient("31", "a@b.com", "pw", session, "homgar")
    return client, session


_APP_UA = "okhttp/4.9.2"


def _test_user_agent_constant():
    ua = getattr(client_mod, "_USER_AGENT", None)
    check("client exposes _USER_AGENT", ua is not None, "constant missing")
    check("_USER_AGENT is the app UA (okhttp/4.9.2)", ua == _APP_UA, f"got {ua!r}")
    check(
        "_USER_AGENT does not contain 'HomeAssistant'",
        ua is not None and "HomeAssistant" not in ua,
        f"got {ua!r}",
    )


async def _test_login_post_sets_ua():
    payload = {
        "code": 0,
        "ts": 1700000000000,
        "data": {"token": "tok", "refreshToken": "r", "tokenExpired": 3600, "user": {}},
    }
    client, session = _make_client(payload)
    ok = await client.login()
    check("login() succeeds against fake server", ok is True)
    post_calls = [c for c in session.calls if c[0] == "post"]
    check("login issues a POST", len(post_calls) == 1, str(session.calls))
    hdrs = post_calls[0][2] if post_calls else {}
    check(
        "login POST sends the app User-Agent",
        hdrs.get("User-Agent") == _APP_UA,
        f"got {hdrs.get('User-Agent')!r}",
    )
    # login() supplies its own headers (Content-Type/lang/appCode); ensure they survive.
    check(
        "login POST preserves caller headers (appCode)",
        hdrs.get("appCode") == "1",
        f"headers={hdrs}",
    )


async def _test_get_path_sets_ua():
    payload = {"code": 0, "data": [], "ts": 1700000000000}
    client, session = _make_client(payload)
    client._token = "tok"
    from datetime import datetime, timedelta, timezone

    client._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await client.list_homes()
    get_calls = [c for c in session.calls if c[0] == "get"]
    check("list_homes issues a GET", len(get_calls) == 1, str(session.calls))
    hdrs = get_calls[0][2] if get_calls else {}
    check(
        "list_homes GET sends the app User-Agent",
        hdrs.get("User-Agent") == _APP_UA,
        f"got {hdrs.get('User-Agent')!r}",
    )


async def _test_ua_overrides_caller_header():
    """A caller/session default of a HomeAssistant UA must be overridden."""
    payload = {"code": 0, "data": [], "ts": 1700000000000}
    client, session = _make_client(payload)
    # Directly exercise the chokepoint with a hostile caller header. _post returns
    # the (async) response object; we only care about what headers it recorded.
    client._post(
        "https://example/test",
        headers={"User-Agent": "HomeAssistant/2026.7 aiohttp/3 Python/3.13", "auth": "T"},
    )
    _, _, hdrs = session.calls[-1]
    check(
        "_post overrides a HomeAssistant User-Agent with the app UA",
        hdrs.get("User-Agent") == _APP_UA,
        f"got {hdrs.get('User-Agent')!r}",
    )
    check("_post preserves other caller headers (auth)", hdrs.get("auth") == "T", f"headers={hdrs}")


def main() -> int:
    print("User-Agent regression tests")
    _test_user_agent_constant()
    asyncio.run(_test_login_post_sets_ua())
    asyncio.run(_test_get_path_sets_ua())
    asyncio.run(_test_ua_overrides_caller_header())
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
