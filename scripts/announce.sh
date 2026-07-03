#!/usr/bin/env bash
#
# Post an announcement to the project Discord announcements channel.
#
# The webhook URL is a SECRET and must never be committed. Provide it via either:
#   1. the DISCORD_WEBHOOK_URL environment variable, or
#   2. a gitignored secrets file (default: repo-root .env, which is already in
#      .gitignore) containing the line:
#          DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxx/yyyy
#      Override the path with ANNOUNCE_ENV_FILE=/path/to/file.
#
# Because the script reads the webhook from disk, an assistant/CI can run it
# without the URL ever passing through a chat transcript or the command line.
#
# Usage:
#   scripts/announce.sh -m "message text"        # inline message
#   scripts/announce.sh -f path/to/message.md    # message from a file
#   scripts/announce.sh -r v3.0.36               # templated release announcement
#   echo "message" | scripts/announce.sh         # message from stdin
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ANNOUNCE_ENV_FILE:-$REPO_ROOT/.env}"

# Load the secrets file only if the webhook isn't already in the environment.
if [[ -z "${DISCORD_WEBHOOK_URL:-}" && -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a; source "$ENV_FILE"; set +a
fi

if [[ -z "${DISCORD_WEBHOOK_URL:-}" ]]; then
    echo "❌ DISCORD_WEBHOOK_URL is not set." >&2
    echo "   Add it to $ENV_FILE (gitignored) or export it in your shell." >&2
    exit 1
fi

MSG=""
RELEASE=""
while getopts ":m:f:r:" opt; do
    case "$opt" in
        m) MSG="$OPTARG" ;;
        f) MSG="$(cat -- "$OPTARG")" ;;
        r) RELEASE="$OPTARG" ;;
        *) echo "Usage: $0 [-m message | -f file | -r vX.Y.Z]  (or pipe via stdin)" >&2; exit 2 ;;
    esac
done

# Build a templated message from a release tag if -r was given.
if [[ -n "$RELEASE" ]]; then
    if ! command -v gh >/dev/null 2>&1; then
        echo "❌ -r needs the gh CLI to read the release notes." >&2
        exit 2
    fi
    TITLE="$(gh release view "$RELEASE" --json name -q .name)"
    URL="$(gh release view "$RELEASE" --json url -q .url)"
    MSG="🚀 **${TITLE}**

📖 Release notes: ${URL}

Update via HACS → restart Home Assistant."
fi

# Fall back to stdin if no message was supplied another way.
if [[ -z "$MSG" ]]; then
    MSG="$(cat)"
fi
if [[ -z "${MSG// }" ]]; then
    echo "❌ No message provided." >&2
    exit 2
fi

# jq handles all JSON escaping (newlines, quotes, unicode) safely.
PAYLOAD="$(jq -n --arg content "$MSG" '{content: $content}')"

RESP_FILE="$(mktemp)"
trap 'rm -f "$RESP_FILE"' EXIT
HTTP_CODE="$(curl -sS -o "$RESP_FILE" -w '%{http_code}' \
    -H "Content-Type: application/json" -X POST \
    -d "$PAYLOAD" "$DISCORD_WEBHOOK_URL")"

# Discord returns 204 No Content on a successful webhook post.
if [[ "$HTTP_CODE" == "204" || "$HTTP_CODE" == "200" ]]; then
    echo "✅ Announcement posted to Discord (HTTP $HTTP_CODE)"
else
    echo "❌ Discord returned HTTP $HTTP_CODE:" >&2
    cat "$RESP_FILE" >&2; echo >&2
    exit 1
fi
