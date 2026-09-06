#!/usr/bin/env python3
"""Regression tests: product image selection from the shipped catalogue.

The catalogue's productImage codes are asset TYPES, not sizes:

  REAL     a colour product photograph  (144x144, on 106 of 107 models)
  BIG      a generic grey category icon (a tap symbol, not the device)
  SMALL    a grey line drawing of the device outline
  EXAMPLE  an in-situ marketing shot

Sizes do not follow the names — HCS021FRF's "SMALL" is 371px while its "BIG"
is 216px. So only REAL is used, and there is deliberately no fallback to the
others: showing a generic tap icon in place of a device photo is worse than
showing no picture at all, because Home Assistant's own icon is a better
generic than the vendor's.

Runs in the ha-test container against the deployed integration at /config.
"""
import sys

sys.path.insert(0, "/config")

from custom_components.homgar.product_images import image_url_for_model  # noqa: E402

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


print("\n🧪 product image selection")

url = image_url_for_model("HTV113FRF")
check("a known model resolves to a REAL photo URL",
      isinstance(url, str) and url.startswith("https://") and url.endswith(".png"),
      f"got {url!r}")

check("the URL is the REAL variant, not the icon or line drawing",
      url == "https://oss3.homgarus.com/us/config/1/product/202508/192639794d2b4aeb93d0058629667309.png",
      f"got {url!r}")

check("lookup is case-insensitive, as model strings arrive verbatim from devices",
      image_url_for_model("htv113frf") == url,
      f"got {image_url_for_model('htv113frf')!r}")

check("an unknown model yields None rather than raising",
      image_url_for_model("NOT-A-REAL-MODEL") is None)

check("an empty model string yields None",
      image_url_for_model("") is None)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
