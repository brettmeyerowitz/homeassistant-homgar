#!/usr/bin/env bash
#
# Render an HTML file to a retina PNG, cropped exactly to its content.
#
# Built for the telemetry infographic (scripts/stats-infographic.template.html)
# but works for any self-contained page. Uses the Chromium that Playwright
# already installs, so there is nothing extra to install.
#
# Usage:
#   scripts/render-infographic.sh page.html out.png [css_width]
#
# Why the two-pass approach: --window-size decides the screenshot height, and
# guessing it either leaves a band of dead background below the content or
# crops the footer off. So pass 1 renders tall at 1x and scans up from the
# bottom for the first row that is not pure background; pass 2 re-renders at
# 2x using that measured height. Deterministic, no manual fiddling.
#
set -euo pipefail

HTML="${1:?usage: render-infographic.sh page.html out.png [css_width]}"
OUT="${2:?usage: render-infographic.sh page.html out.png [css_width]}"
WIDTH="${3:-1200}"
PROBE_H=2000

CHROME="$(find "$HOME/Library/Caches/ms-playwright" -maxdepth 3 \
    -name 'chrome-headless-shell' -type f 2>/dev/null | sort | tail -1)"
if [[ -z "$CHROME" ]]; then
    echo "❌ No Playwright chrome-headless-shell found." >&2
    echo "   Install one with: npx playwright install chromium" >&2
    exit 1
fi

PROBE="$(mktemp -t infographic).png"
trap 'rm -f "$PROBE"' EXIT

"$CHROME" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --window-size="${WIDTH},${PROBE_H}" --default-background-color=0d1117ff \
    --screenshot="$PROBE" "file://$(cd "$(dirname "$HTML")" && pwd)/$(basename "$HTML")" \
    >/dev/null 2>&1

HEIGHT="$(python3 - "$PROBE" <<'PY'
import struct, sys, zlib
data = open(sys.argv[1], 'rb').read()
pos, idat, ct = 8, b'', 6
while pos < len(data):
    ln = struct.unpack('>I', data[pos:pos+4])[0]
    typ = data[pos+4:pos+8]
    chunk = data[pos+8:pos+8+ln]
    if typ == b'IHDR':
        w, h, _bd, ct = struct.unpack('>IIBB', chunk[:10])
    elif typ == b'IDAT':
        idat += chunk
    elif typ == b'IEND':
        break
    pos += 12 + ln
raw = zlib.decompress(idat)
bpp = 4 if ct == 6 else 3
stride = w * bpp
prev = bytearray(stride)
last = 0
i = 0
rows = []
for _y in range(h):
    f = raw[i]; i += 1
    line = bytearray(raw[i:i+stride]); i += stride
    if f == 1:
        for x in range(bpp, stride): line[x] = (line[x] + line[x-bpp]) & 255
    elif f == 2:
        for x in range(stride): line[x] = (line[x] + prev[x]) & 255
    elif f == 3:
        for x in range(stride):
            a = line[x-bpp] if x >= bpp else 0
            line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
    elif f == 4:
        for x in range(stride):
            a = line[x-bpp] if x >= bpp else 0
            c = prev[x-bpp] if x >= bpp else 0
            b = prev[x]; p = a + b - c
            pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
            pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            line[x] = (line[x] + pr) & 255
    rows.append(bytes(line)); prev = line
bg = rows[-1][:bpp]
for y, r in enumerate(rows):
    if any(r[x:x+bpp] != bg for x in range(0, stride, bpp)):
        last = y
print(last + 1 + 40)   # + bottom breathing room
PY
)"

"$CHROME" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
    --window-size="${WIDTH},${HEIGHT}" --default-background-color=0d1117ff \
    --screenshot="$OUT" "file://$(cd "$(dirname "$HTML")" && pwd)/$(basename "$HTML")" \
    >/dev/null 2>&1

echo "✅ ${OUT}  (${WIDTH}x${HEIGHT} css → $(sips -g pixelWidth -g pixelHeight "$OUT" \
    | awk '/pixelWidth/{w=$2}/pixelHeight/{h=$2}END{print w"x"h}') px, $(du -h "$OUT" | cut -f1))"
