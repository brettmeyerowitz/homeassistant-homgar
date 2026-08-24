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
#   scripts/announce.sh -e path/to/embed.json    # rich embed (full webhook JSON)
#   scripts/announce.sh -i chart.png -m "caption" # attach an image (multipart)
#   echo "message" | scripts/announce.sh         # message from stdin
#
# Add -n to print the exact payload and exit without posting (dry run).
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
EMBED_FILE=""
IMAGE_FILE=""
DRY_RUN=0
while getopts ":m:f:r:e:i:n" opt; do
    case "$opt" in
        m) MSG="$OPTARG" ;;
        f) MSG="$(cat -- "$OPTARG")" ;;
        r) RELEASE="$OPTARG" ;;
        e) EMBED_FILE="$OPTARG" ;;
        i) IMAGE_FILE="$OPTARG" ;;
        n) DRY_RUN=1 ;;
        *) echo "Usage: $0 [-m message | -f file | -r vX.Y.Z | -e embed.json] [-i image] [-n]  (or pipe via stdin)" >&2; exit 2 ;;
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

# A -e file is a complete webhook payload (embeds, and optionally content), so
# it bypasses message assembly entirely.
if [[ -n "$EMBED_FILE" ]]; then
    if [[ ! -f "$EMBED_FILE" ]]; then
        echo "❌ Embed file not found: $EMBED_FILE" >&2
        exit 2
    fi
    if ! PAYLOAD="$(jq -e '.' -- "$EMBED_FILE")"; then
        echo "❌ Embed file is not valid JSON: $EMBED_FILE" >&2
        exit 2
    fi
    if ! jq -e 'has("embeds") or has("content")' >/dev/null <<<"$PAYLOAD"; then
        echo "❌ Embed file must contain \"embeds\" and/or \"content\" at the top level." >&2
        exit 2
    fi
else
    # Fall back to stdin if no message was supplied another way. An image is a
    # message in its own right, so a caption stays optional when -i is used.
    if [[ -z "$MSG" && -z "$IMAGE_FILE" ]]; then
        MSG="$(cat)"
    fi
    if [[ -z "${MSG// }" && -z "$IMAGE_FILE" ]]; then
        echo "❌ No message provided." >&2
        exit 2
    fi

    # jq handles all JSON escaping (newlines, quotes, unicode) safely.
    PAYLOAD="$(jq -n --arg content "$MSG" '{content: $content}')"
fi

if [[ -n "$IMAGE_FILE" && ! -f "$IMAGE_FILE" ]]; then
    echo "❌ Image file not found: $IMAGE_FILE" >&2
    exit 2
fi

# Dry run: show exactly what would be posted, touch nothing.
if [[ "$DRY_RUN" == "1" ]]; then
    echo "🔍 Dry run — this payload would be POSTed to the webhook:"
    jq '.' <<<"$PAYLOAD"
    [[ -n "$IMAGE_FILE" ]] && echo "   + attachment: $IMAGE_FILE ($(du -h "$IMAGE_FILE" | cut -f1))"
    exit 0
fi

RESP_FILE="$(mktemp)"
trap 'rm -f "$RESP_FILE"' EXIT
if [[ -n "$IMAGE_FILE" ]]; then
    HTTP_CODE="$(curl -sS -o "$RESP_FILE" -w '%{http_code}' -X POST \
        -F "payload_json=$PAYLOAD" \
        -F "files[0]=@${IMAGE_FILE}" "$DISCORD_WEBHOOK_URL")"
else
    HTTP_CODE="$(curl -sS -o "$RESP_FILE" -w '%{http_code}' \
        -H "Content-Type: application/json" -X POST \
        -d "$PAYLOAD" "$DISCORD_WEBHOOK_URL")"
fi

# Discord returns 204 No Content on a successful webhook post.
if [[ "$HTTP_CODE" == "204" || "$HTTP_CODE" == "200" ]]; then
    echo "✅ Announcement posted to Discord (HTTP $HTTP_CODE)"
else
    echo "❌ Discord returned HTTP $HTTP_CODE:" >&2
    cat "$RESP_FILE" >&2; echo >&2
    exit 1
fi
