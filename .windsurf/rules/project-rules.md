---
trigger: always_on
---

# HomGar Integration — Project Rules

## Testing
- **Use the `ha-test` Docker container for Home Assistant integration validation**
- Pure offline/unit-style tests may run on the host machine when they do not depend on Home Assistant runtime, Docker state, or container-only paths
- After copying files to Docker, always restart the container to clear `.pyc` cache
- Run `bash scripts/pre-commit-docker-test.sh` before every commit
- **NEVER use `docker exec ha-test python3 -c "..."` inline text blocks — ALWAYS write the script to `/tmp/script.py` first, then `docker cp /tmp/script.py ha-test:/tmp/script.py && docker exec ha-test python3 /tmp/script.py`. No exceptions.**

## GitHub
- Use `gh` CLI for all GitHub operations (releases, issue comments, PRs) — never instruct the user to do it manually in the browser
- For GitHub releases: `gh release create "vX.X.X" --title "vX.X.X" --notes "..."`
- For issue comments: `gh issue comment <number> --body "..."`
- When writing multi-line content for `gh` commands, write it to a temp file first, then pass with `--notes-file` or `--body-file` — never use inline heredocs or text blocks which break in zsh

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

## README maintenance
- When adding a new supported device model, add it to the flat model list in the `## Supported Devices` section of `README.md`
- When adding new decoded sensor fields, add them to the entities table in `README.md`
- The pre-commit script checks README version matches manifest — it will fail if out of sync

## Code style
- Decoding is data-driven via `product_models.json` — `decode_payload(model, payload)` in `decoder.py` is used by both REST poll (`coordinator.py`) and MQTT (`coordinator_mqtt.py`)
- New device support typically only requires an entry in `product_models.json` — no separate decoder file needed unless the device has a completely custom format (e.g. HIC801W)
- Valve sub-device models are looked up by `addr` from `hub["subDevices"]` at MQTT decode time
