# Test Corpus

This document tracks the real payload samples currently represented in the public regression corpus.

## Covered Models

| Model | Sample count | Source |
| --- | ---: | --- |
| HCS0530THO | 2 | live captures |
| HCS014ARF | 8 | GitHub issue #21 |
| HCS021FRF | 1 | live capture |
| HCS008FRF | 1 | live capture |
| HCS030FRF | 1 | GitHub issue #27 |
| HCS0528ARF | 2 | GitHub issue #18 |
| HCS0565ARF | 2 | GitHub issue #23 |
| HTV113FRF | 2 | live captures |
| HTV213FRF | 8 | GitHub issues #11, #17 |
| HTV245FRF | 2 | GitHub issues #10, #17 |
| HTV0537FRF | 2 | GitHub issue #26 |
| HTV0542FRF | 2 | GitHub issue #22 |
| HIC801W | 1 | GitHub issue #20 |
| HTP115FRF | 1 | GitHub issue #31 |
| HCS012ARF | 2 | GitHub issue #30 |
| HWS019WRF-V2 | 1 | GitHub issue #29 |

## Goals

The corpus should grow by issue-driven regressions, not by synthetic examples only.

When adding a new sample:
- preserve the original raw payload
- record the source issue number when available
- keep expected values limited to the fields needed for regression safety
- prefer real app-confirmed readings when possible
