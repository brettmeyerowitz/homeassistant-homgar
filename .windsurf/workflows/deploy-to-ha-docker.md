---
description: Deploy integration to the ha-test Docker container for testing
---

## Deploy and restart

// turbo
```
docker cp custom_components/homgar ha-test:/config/custom_components/ && docker restart ha-test
```

## Wait for startup and confirm connected

// turbo
```
sleep 25 && docker logs ha-test --since=27s 2>&1 | grep -v DEBUG | grep -E "connected successfully|subscribeStatus|Found.*devices|forcing fresh login"
```

## Watch MQTT valve updates live

// turbo
```
docker logs ha-test -f 2>&1 | grep -E "MQTT update|coordinator_mqtt|sub_devices|Updated sensor|Decoded valve"
```

## Key rules
- **Always test inside the `ha-test` Docker container — never locally**
- The container is named `ha-test`
- After copying files, always restart the container to clear `.pyc` cache
- HomGar account uses `homgar` app_type; RainPoint account uses `rainpoint` app_type — never mix credentials
- MQTT uses `securemode=2` with a fresh HMAC-SHA1 timestamp on every connect
- Subscribe only to 5 `/sys/` topics — no wildcards, no `/user/` topics (causes `rc=7` disconnect)
