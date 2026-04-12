# Testing

## Test Layers

The project should maintain two test layers:

1. Offline/unit-style tests
- fast fixture validation
- decoder regression tests
- config-flow helper tests
- MQTT payload parsing tests

2. Docker-based integration validation
- Home Assistant startup validation in `ha-test`
- import/runtime verification
- release-gate regression checks

## Required Validation Before Commit

Always run:

```bash
bash scripts/pre-commit-docker-test.sh
```

This is the release/commit gate for Home Assistant integration validation.

## Host vs Docker

Allowed on the host:
- pure offline tests that do not depend on Home Assistant runtime
- fixture schema checks
- static regression tests over payload fixtures

Example host-side payload corpus run:

```bash
python3 tests/run_payload_fixture_tests.py
```

Required in `ha-test`:
- Home Assistant startup validation
- integration flow checks that depend on HA internals
- container-path-dependent scripts

## Payload Corpus

Real payloads from GitHub issues and live device captures should be stored under:

```text
tests/fixtures/payloads/
```

Use one file per model and keep a flat index in:

```text
tests/fixtures/payload_index.json
```

Each sample should capture:
- model
- source issue number if known
- format (`tlv`, `legacy`, `mqtt`)
- raw payload
- expected decoded subset
- notes

## Adding New Regression Coverage

When a user reports a decoder issue:
1. capture the raw payload and device model
2. link it to the GitHub issue number
3. add the payload to the fixture corpus
4. add or extend regression coverage
5. update `docs/test-corpus.md`

The fixture corpus runner lives at:

```text
tests/run_payload_fixture_tests.py
```

## Container Script Rules

For non-trivial Python inside the container:
- write a temp script locally
- `docker cp` it into `ha-test`
- run it there

Do not use inline `docker exec ... python3 -c "..."` for substantial scripts.
