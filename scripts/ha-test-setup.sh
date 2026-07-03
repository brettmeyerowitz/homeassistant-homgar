#!/usr/bin/env bash
#
# Spin up (or refresh) the local Home Assistant "ha-test" container used for
# integration validation and manual release testing.
#
# This is the container that scripts/pre-commit-docker-test.sh expects to find
# running. See docs/testing.md for the full workflow.
#
# Usage:
#   bash scripts/ha-test-setup.sh              # create if missing, else start + redeploy
#   bash scripts/ha-test-setup.sh --recreate   # destroy and rebuild from scratch
#
# Override defaults via env vars:
#   HA_TEST_CONTAINER (default: ha-test)
#   HA_TEST_IMAGE     (default: ghcr.io/home-assistant/home-assistant:stable)
#   HA_TEST_VOLUME    (default: ha-test-config)   # named docker volume holding /config
#   HA_TEST_PORT      (default: 8123)
#
set -euo pipefail

CONTAINER="${HA_TEST_CONTAINER:-ha-test}"
IMAGE="${HA_TEST_IMAGE:-ghcr.io/home-assistant/home-assistant:stable}"
VOLUME="${HA_TEST_VOLUME:-ha-test-config}"
PORT="${HA_TEST_PORT:-8123}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v docker >/dev/null 2>&1 || { echo "❌ docker not found on PATH"; exit 1; }
docker info >/dev/null 2>&1 || { echo "❌ docker daemon not running"; exit 1; }

if [[ "${1:-}" == "--recreate" ]]; then
    echo "🧹 Removing existing '$CONTAINER' container..."
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
fi

if docker inspect "$CONTAINER" >/dev/null 2>&1; then
    echo "▶️  Container '$CONTAINER' exists; starting it..."
    docker start "$CONTAINER" >/dev/null
else
    echo "⬇️  Pulling $IMAGE (first run only, ~1GB)..."
    docker pull "$IMAGE"
    echo "🚀 Creating container '$CONTAINER' (host port $PORT → 8123, config volume '$VOLUME')..."
    docker run -d \
        --name "$CONTAINER" \
        --restart unless-stopped \
        -p "${PORT}:8123" \
        -v "${VOLUME}:/config" \
        "$IMAGE" >/dev/null
fi

echo "⏳ Waiting for Home Assistant to initialize..."
READY=0
for _ in $(seq 1 60); do
    if docker exec "$CONTAINER" sh -c 'grep -q "Home Assistant initialized" /config/home-assistant.log' 2>/dev/null; then
        READY=1
        break
    fi
    sleep 3
done
if [[ "$READY" -ne 1 ]]; then
    echo "⚠️  Did not see 'Home Assistant initialized' within ~3 min. Check: docker logs $CONTAINER"
fi

echo "📦 Deploying custom_components/homgar into '$CONTAINER'..."
docker exec "$CONTAINER" mkdir -p /config/custom_components
docker cp "$REPO_ROOT/custom_components/homgar" "$CONTAINER:/config/custom_components/" >/dev/null
docker restart "$CONTAINER" >/dev/null

cat <<EOF

✅ '$CONTAINER' is up at http://localhost:${PORT}

Next steps (one-time, requires your HomGar/RainPoint account):
  1. Open http://localhost:${PORT} and complete Home Assistant onboarding.
  2. Settings → Devices & Services → Add Integration → "HomGar/RainPoint".
  3. Sign in to create a config entry. The integration now loads on every restart.

Day-to-day:
  • Re-deploy code + run the full validation gate:
        bash scripts/pre-commit-docker-test.sh
  • Tail logs:
        docker exec $CONTAINER tail -f /config/home-assistant.log
  • Stop / start:
        docker stop $CONTAINER   |   docker start $CONTAINER
EOF
