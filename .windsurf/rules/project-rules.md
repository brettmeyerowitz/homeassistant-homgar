---
trigger: always_on
---

# HomGar Integration — Project Rules

## Testing
- **Always test inside the `ha-test` Docker container — never locally**
- Never run Python test scripts directly on the host machine
- After copying files to Docker, always restart the container to clear `.pyc` cache
- Run `bash scripts/pre-commit-docker-test.sh` before every commit

## GitHub
- Use `gh` CLI for all GitHub operations (releases, issue comments, PRs) — never instruct the user to do it manually in the browser
- For GitHub releases: `gh release create "vX.X.X" --title "vX.X.X" --notes "..."`
- For issue comments: `gh issue comment <number> --body "..."`
- When writing multi-line content for `gh` commands, write it to a temp file first, then pass with `--notes-file` or `--body-file` — never use inline heredocs or text blocks which break in zsh

## File operations
- Write scripts and test content to temp files (e.g. `/tmp/test_xyz.py`) rather than passing as inline text blocks to shell commands
- Use `docker cp <file> ha-test:/tmp/<file>` then `docker exec ha-test python3 /tmp/<file>` for running test scripts in Docker

## MQTT rules
- MQTT uses `securemode=2` with a fresh HMAC-SHA1 timestamp generated on every connect/reconnect — never reuse stale credentials
- Subscribe only to 5 `/sys/` topics — no wildcards, no `/user/` topics (causes `rc=7` disconnect)
- HomGar account (`homgar` app_type) and RainPoint account (`rainpoint` app_type) are separate — never mix credentials between accounts
- Physical device credentials come from `subscribeStatus` API call — not from login response

## Accounts
- Two accounts: HomGar (`homgar` app_type, area code `1`) and RainPoint (`rainpoint` app_type, area code `27`)
- Credentials are stored in the HA config entries inside the `ha-test` Docker container — retrieve with:
  `docker exec ha-test cat /config/.storage/core.config_entries | python3 -m json.tool | grep -A5 homgar`
- Virtual MQTT product key and host are returned by the `subscribeStatus` API call at runtime — do not hardcode
- Never mix HomGar and RainPoint credentials between accounts

## README maintenance
- When adding a new supported device, update the device compatibility table in `README.md`
- When bumping the version, update the `manifest.json` code snippet version in `README.md`
- When adding new entities for a device, update the entities column in the device table
- The pre-commit script checks README version matches manifest — it will fail if out of sync

## Code style
- `DECODER_REGISTRY` in `coordinator.py` is the single source of truth for model→decoder mappings — both REST poll and MQTT paths use it
- New device support requires: decoder file → export chain → `const.py` constant → `DECODER_REGISTRY` entry → sensor entities
- Valve sub-device models are looked up by `addr` from `hub["subDevices"]` at MQTT decode time

