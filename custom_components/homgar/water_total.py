"""Derive a cumulative water total from per-session volumes.

Issue #96: valves such as the HTV245FRF report only ``STA_LASTUSAGE`` — the
volume of the most recent watering session — and carry no cumulative counter at
all (no ``STA_WATER_TOTAL``, no ``STA_TOTAL_TODAY``). Home Assistant's Energy /
water dashboard needs a monotonically increasing meter, so there was nothing on
these devices to give it.

This accumulates completed sessions into a running total instead.

The session key is the device's own event timestamp, not the volume. Detecting
"a new session" by watching the volume change is wrong in a way that loses data
silently: two consecutive sessions of identical volume — the normal outcome of a
fixed-duration schedule — look like one unchanged reading. The timestamp
distinguishes them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def session_key(source: Mapping[str, Any]) -> int | None:
    """Return the session's event time as a Unix timestamp, or None.

    The two decode paths expose the same event differently, and reading only one
    of them shipped a sensor that could never count anything (v3.0.48, #96):

    * legacy payloads set ``event_time_raw`` (int) *and* ``event_time`` (ISO)
    * TLV payloads — the HTV245FRF and most current hardware — set only
      ``event_time`` as an ISO-8601 string

    Keying on ``event_time_raw`` alone therefore worked on exactly the devices
    nobody reported, and never on the ones that did. Accept either shape.
    """
    raw = source.get("event_time_raw")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw > 0:
        return int(raw)

    value = source.get("event_time")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return int(value)
    if isinstance(value, str) and value:
        try:
            return int(datetime.fromisoformat(value).timestamp())
        except ValueError:
            # A malformed timestamp must not become a key: a wrong one either
            # double counts a session or hides a real one.
            return None
    return None


def accumulate_session(
    total: float,
    last_event_time: int | None,
    event_time: int | None,
    volume: float | None,
) -> tuple[float, int | None]:
    """Fold one polled reading into a running total.

    Returns the new ``(total, last_event_time)`` pair. Pure, so the caller owns
    persistence and this stays trivially testable.

    The total feeds a ``TOTAL_INCREASING`` sensor, where any decrease is read by
    Home Assistant as a meter reset and silently starts a new accumulation
    cycle. Every branch below therefore either adds a non-negative amount or
    leaves the total alone; none can reduce it.
    """
    # Nothing identifiable to count. Leave both values untouched rather than
    # guessing, so a malformed poll cannot corrupt a good total.
    if event_time is None:
        return total, last_event_time

    # Same session seen again. The coordinator polls every 120s while a
    # completed session's volume just sits there, so this is the common path and
    # must not accumulate.
    if last_event_time is not None and event_time <= last_event_time:
        return total, last_event_time

    # A genuinely new session, but no volume in this payload yet. Hold the old
    # key rather than adopting it: payloads can be partial, and the volume may
    # arrive on a later poll for this same session. Advancing now would mean
    # that session is never counted. Holding is safe — while the volume stays
    # absent nothing accumulates, and once it appears it is counted exactly
    # once, because the next comparison still sees a newer event time.
    if volume is None:
        return total, last_event_time

    # Present but impossible. Unlike a missing value this will not improve on a
    # later poll, so adopt the key and skip it — a negative would otherwise
    # reduce a TOTAL_INCREASING total, which Home Assistant reads as a meter
    # reset. Zero falls through below: a session that ran without flow is a
    # real measurement and adding it is a no-op that correctly advances the key.
    if volume < 0:
        return total, event_time

    return total + volume, event_time
