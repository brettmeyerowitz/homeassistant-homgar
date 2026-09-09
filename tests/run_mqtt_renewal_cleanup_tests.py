#!/usr/bin/env python3
"""Regression tests: a failed MQTT replacement client must not be abandoned.

Issue #110, reported by @BastiPrivat with a diagnosis and a patch.

Two defects, both about ownership of a client nobody holds a reference to:

1. In ``_async_renew_mqtt_subscription`` the replacement client is only stored
   in ``entry_data["mqtt_client"]`` on success. When ``connect()`` returns
   False the code scheduled a retry and returned, never calling
   ``disconnect()`` — and because it was never stored, the unload path could
   not clean it up either. That matters because ``connect()`` reaching False
   does NOT mean nothing is running: ``_connect_client()`` calls
   ``loop_start()`` before ``_wait_for_connection()`` polls for ten seconds,
   so the paho network thread is already going. Every retry built another one.

2. ``_reconnect_loop`` checked ``_shutdown_requested`` before its backoff and
   not after. With the backoff reaching 300 seconds, a client shut down during
   that window still woke up and opened a connection up to five minutes later.

Runs in the ha-test container against the deployed integration at /config.
"""
import asyncio
import sys
import threading
import time

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


# ---------------------------------------------------------------- defect 2
print("\n🧪 a client shut down during backoff must not connect afterwards")

from custom_components.homgar.mqtt_client import HomGarMQTTClient  # noqa: E402

client = HomGarMQTTClient(
    product_key="pk", device_name="dn", device_secret="ds",
    mqtt_host="127.0.0.1", on_message_callback=lambda d: None, mqtt_port=1883,
)

attempts = []
client._connect_client = lambda: attempts.append(time.monotonic())
client._wait_for_connection = lambda *a, **kw: True

started = time.monotonic()
t = threading.Thread(target=client._reconnect_loop, daemon=True)
t.start()
time.sleep(0.3)          # let it enter the backoff
client._shutdown_requested = True
client.disconnect()      # a real shutdown, as the unload path would do
t.join(timeout=5)

elapsed = time.monotonic() - started
check("the reconnect loop stops promptly instead of sleeping out its backoff",
      not t.is_alive(), f"still running after {elapsed:.1f}s")
check("no connection is attempted after shutdown",
      attempts == [], f"got {len(attempts)} attempt(s)")


# ---------------------------------------------------------------- defect 1
print("\n🧪 a replacement client that fails to connect is disconnected")

from custom_components.homgar import _async_renew_mqtt_subscription  # noqa: E402
from custom_components.homgar import const as hg_const  # noqa: E402
import custom_components.homgar as hg  # noqa: E402

events = []


class FakeClient:
    """Stands in for HomGarMQTTClient: connect fails, as on a timeout."""

    def __init__(self, **kw):
        events.append("constructed")

    def connect(self):
        events.append("connect")
        return False

    def disconnect(self):
        events.append("disconnect")


class FakeApi:
    async def subscribe_status(self, hid, hubs, hids):
        return {
            "deviceName": "dn", "deviceSecret": "ds", "productKey": "pk",
            "mqttHostUrl": "broker.example.com:1883", "expire": None,
        }


class FakeCoordinator:
    data = {"hubs": [{"mid": 1, "name": "Hub"}]}

    async def handle_mqtt_update(self, data):
        return None


class FakeEntry:
    entry_id = "e1"
    title = "test"
    data = {hg_const.CONF_HIDS: [1]}


class FakeHass:
    def __init__(self):
        self.data = {hg_const.DOMAIN: {"e1": {
            "client": FakeApi(), "coordinator": FakeCoordinator(), "mqtt_client": None}}}
        self.loop = asyncio.get_event_loop()

    async def async_add_executor_job(self, fn, *args):
        return fn(*args)


async def main():
    hg.HomGarMQTTClient = FakeClient          # patch the name the module calls
    hg._schedule_mqtt_renewal_retry = lambda *a, **kw: events.append("retry_scheduled")

    result = await _async_renew_mqtt_subscription(FakeHass(), FakeEntry())

    check("the failed branch still returns False", result is False, f"got {result!r}")
    check("the failed replacement client is disconnected",
          "disconnect" in events, f"events={events}")
    check("it is disconnected BEFORE the retry is scheduled",
          "disconnect" in events and "retry_scheduled" in events
          and events.index("disconnect") < events.index("retry_scheduled"),
          f"events={events}")

asyncio.run(main())

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
