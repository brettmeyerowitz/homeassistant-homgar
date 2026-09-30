# Test Corpus

This document tracks the real payload samples currently represented in the public regression corpus.

## Covered Models

| Model | Sample count | Source |
| --- | ---: | --- |
| HCS008FRF | 2 | live captures |
| HCS012ARF | 3 | GitHub issue #30, maintainer device, 1 unverified |
| HCS014ARF | 9 | GitHub issue #21, live captures, 3 unverified |
| HCS021FRF | 4 | live captures, 1 unverified |
| HCS030FRF | 1 | GitHub issue #27 |
| HCS044FRF | 3 | live captures |
| HCS0528ARF | 2 | GitHub issue #18 |
| HCS0530THO | 3 | live captures |
| HCS0565ARF | 2 | GitHub issue #23 |
| HIC801W | 9 | GitHub issue #20 and live captures |
| HIC819W-6 | 1 | live capture |
| HTP115FRF | 1 | GitHub issue #31 |
| HTP159W | 1 | 1 unverified |
| HTV0537FRF | 2 | GitHub issue #26 |
| HTV0542FRF | 2 | GitHub issue #22 |
| HTV103FRF | 3 | reporter, app-verified (issue #81) |
| HTV113FRF | 8 | live captures |
| HTV213FRF | 9 | GitHub issues #11, #17 and live captures |
| HTV245FRF | 5 | GitHub issues #10, #17, live captures, 1 unverified |
| HWS019WRF-V2 | 2 | GitHub issue #29 and live captures |
## Where a sample came from

Every sample declares a `source_type`. The first three assert that the payload
appears verbatim in the source named:

| `source_type` | meaning |
| --- | --- |
| `github_issue` | quoted in the body or a comment of `source_issue` |
| `github_issue_comment` | quoted in a comment of `source_issue` |
| `reporter_app_verified` | supplied by a reporter alongside app screenshots of the same readings |
| `live_capture` | captured from a real device |
| `maintainer_device` | captured from the maintainer's own hardware |
| `unverified` | origin never established - see the sample's `provenance` field |

`unverified` exists because several samples cited an issue that does not contain
them. Some are probably real captures tagged with the issue that motivated the
work rather than the issue they were quoted in, but that cannot be checked after
the fact, so they say so. **An `unverified` sample must not be cited as evidence
on its own** - if a decoder claim rests on one, find a second source for it.

`tests/run_fixture_provenance_tests.py` enforces what can be checked offline: a
known `source_type`, an issue number behind any claim to one, an explanation on
anything `unverified`, and - the one that matters most - that no payload string
is filed under more than one model. A single payload cannot be the state of two
different devices, and that is the shape a fabricated sample takes.


## Goals

The corpus should grow by issue-driven regressions, not by synthetic examples only.

When adding a new sample:
- preserve the original raw payload, exactly as it arrived
- record the source issue number when available, and a `source_type` that is
  honest about whether the payload is actually in that issue
- keep expected values limited to the fields needed for regression safety
- prefer real app-confirmed readings when possible
