#!/usr/bin/env python3
"""Regression tests: product images are fetched once, then served locally.

The point of caching is privacy, not speed. entity_picture must point at Home
Assistant, never at the vendor's CDN, so that a dashboard render never tells
oss3.homgarus.com who is looking or when. One fetch per model, ever.

A failed fetch is a normal case (a model newer than the catalogue, a blocked
CDN) and must not retry on every reload, or a dead CDN turns into a stall on
every restart.

Runs in the ha-test container against the deployed integration at /config.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/config")

from custom_components.homgar import product_images  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Counts calls so 'fetched once, ever' is an assertion, not a hope."""

    def __init__(self, status=200, body=b"\x89PNG\r\n\x1a\nfake"):
        self.calls = 0
        self._status = status
        self._body = body

    def get(self, url, **kw):
        self.calls += 1
        return FakeResponse(self._status, self._body)


class FakeHass:
    def __init__(self, root):
        self._root = Path(root)
        # Cache state lives here rather than in a module global, so a fresh
        # hass is a fresh cache and production needs no test-only reset hook.
        self.data = {}

    class _Config:
        def __init__(self, root):
            self._root = root

        def path(self, *parts):
            return str(Path(self._root).joinpath(*parts))

    @property
    def config(self):
        return self._Config(self._root)

    async def async_add_executor_job(self, fn, *args):
        return fn(*args)


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        hass = FakeHass(tmp)
        session = FakeSession()

        first = await product_images.async_ensure_cached(hass, session, "HTV113FRF")
        check("a known model is fetched and cached to disk",
              first is not None and Path(first).exists(), f"got {first!r}")
        check("exactly one network call was made", session.calls == 1, f"calls={session.calls}")

        second = await product_images.async_ensure_cached(hass, session, "HTV113FRF")
        check("a second request reuses the cache", second == first, f"got {second!r}")
        check("no second network call was made", session.calls == 1, f"calls={session.calls}")

    # A model with no catalogue entry must never reach the network at all.
    with tempfile.TemporaryDirectory() as tmp:
        hass = FakeHass(tmp)
        s2 = FakeSession()
        check("an unknown model returns None without fetching",
              await product_images.async_ensure_cached(hass, s2, "NOPE-1234") is None and s2.calls == 0,
              f"calls={s2.calls}")

    # A failing CDN must be remembered, not retried on every reload. A fresh
    # directory, because the on-disk cache deliberately survives restarts and
    # a file left by an earlier scenario would mask the fetch entirely.
    with tempfile.TemporaryDirectory() as tmp:
        hass = FakeHass(tmp)
        s3 = FakeSession(status=404, body=b"")
        r1 = await product_images.async_ensure_cached(hass, s3, "HTV113FRF")
        r2 = await product_images.async_ensure_cached(hass, s3, "HTV113FRF")
        check("a failed fetch yields None", r1 is None and r2 is None, f"got {r1!r} {r2!r}")
        check("a failed fetch is not retried on the next request",
              s3.calls == 1, f"calls={s3.calls}")

asyncio.run(main())
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
