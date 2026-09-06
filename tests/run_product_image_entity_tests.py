#!/usr/bin/env python3
"""Regression tests: the per-device product image entity.

Home Assistant's image platform serves the bytes itself, so the integration
needs no HTTP view of its own and entity_picture never points at the vendor's
CDN — the browser only ever talks to Home Assistant.

One image entity per device, deliberately: setting entity_picture on the shared
sensor base would put the same photo on every battery, signal, temperature and
moisture row, replacing the state icons that make a device page readable.

Runs in the ha-test container against the deployed integration at /config.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/config")

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


SENSOR_INFO = {
    "hid": "h1", "mid": "235522", "addr": 6,
    "sub_name": "1 Zone Smart Hose Timer", "model": "HTV113FRF",
}


class FakeBus:
    """ImageEntity's constructor builds an httpx client, which registers a
    shutdown listener on the bus."""

    def async_listen_once(self, *a, **kw):
        return lambda: None


class FakeCoordinator:
    def __init__(self):
        self.data = {"sensors": {"s1": {"data": {"battery_level": 100}}}, "hubs": []}
        self.last_update_success = True

    def async_add_listener(self, *a, **kw):
        return lambda: None


async def main():
    from custom_components.homgar.image import HomGarProductImage

    with tempfile.TemporaryDirectory() as tmp:
        class FakeHass:
            data = {}
            loop = asyncio.get_running_loop()
            bus = FakeBus()

            class config:  # noqa: N801
                @staticmethod
                def path(*parts):
                    return str(Path(tmp).joinpath(*parts))

            async def async_add_executor_job(self, fn, *args):
                return fn(*args)

        hass = FakeHass()
        # Pre-seed the cache so the entity never needs the network in tests.
        img = Path(tmp) / "homgar_images" / "HTV113FRF.png"
        img.parent.mkdir(parents=True, exist_ok=True)
        img.write_bytes(b"\x89PNG\r\n\x1a\nfake-bytes")

        ent = HomGarProductImage(hass, FakeCoordinator(), "s1", SENSOR_INFO, "hose_timer")

        check("declares PNG, not the platform default JPEG",
              ent.content_type == "image/png", f"got {ent.content_type!r}")

        check("has a stable unique_id scoped to the device",
              isinstance(ent.unique_id, str) and "235522" in ent.unique_id and "6" in ent.unique_id,
              f"got {ent.unique_id!r}")

        check("is attached to the same device as that device's sensors",
              ent.device_info.get("identifiers"), f"got {ent.device_info!r}")

        data = await ent.async_image()
        check("serves the cached bytes", data == b"\x89PNG\r\n\x1a\nfake-bytes", f"got {data!r}")

        # An ImageEntity's state IS its last-updated time. Without one the row
        # reads "Unknown" in the UI while serving bytes perfectly well — which
        # is exactly how this shipped until it was spotted on a device page.
        check("records a last-updated time, so the entity state is not Unknown",
              ent.image_last_updated is not None,
              f"got {ent.image_last_updated!r}")

    # A model with no photo must produce no bytes rather than raising.
    with tempfile.TemporaryDirectory() as tmp2:
        class FakeHass2(FakeHass):
            data = {}

            class config:  # noqa: N801
                @staticmethod
                def path(*parts):
                    return str(Path(tmp2).joinpath(*parts))

        info = dict(SENSOR_INFO, model="NOT-A-REAL-MODEL")
        ent2 = HomGarProductImage(FakeHass2(), FakeCoordinator(), "s1", info, "x")
        check("a model with no photo yields None, not an exception",
              await ent2.async_image() is None)

asyncio.run(main())
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
