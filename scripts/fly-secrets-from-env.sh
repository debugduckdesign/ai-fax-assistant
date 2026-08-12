#!/usr/bin/env bash
# Push API secrets from local .env to Fly (ai-fax-assistant-api).
# Prerequisites: flyctl installed + `fly auth login`
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API_APP="${API_APP:-ai-fax-assistant-api}"
WEB_APP="${WEB_APP:-ai-fax-assistant-web}"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy .env.example and fill values first."
  exit 1
fi

FLY="$(command -v flyctl || command -v fly || true)"
if [[ -z "$FLY" && -x "$HOME/.fly/bin/flyctl" ]]; then
  FLY="$HOME/.fly/bin/flyctl"
fi
if [[ -z "$FLY" ]]; then
  echo "Install flyctl first: https://fly.io/docs/hands-on/install-flyctl/"
  exit 1
fi

# shellcheck disable=SC1090
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY missing in .env}"
: "${ELEVENLABS_API_KEY:?ELEVENLABS_API_KEY missing in .env}"
: "${ELEVENLABS_AGENT_ID:?ELEVENLABS_AGENT_ID missing in .env}"
: "${ELEVENLABS_AGENT_PHONE_NUMBER_ID:?ELEVENLABS_AGENT_PHONE_NUMBER_ID missing in .env}"
: "${ELEVENLABS_WEBHOOK_SECRET:?ELEVENLABS_WEBHOOK_SECRET missing in .env}"
: "${ADMIN_USERNAME:?ADMIN_USERNAME missing in .env}"
: "${ADMIN_PASSWORD:?ADMIN_PASSWORD missing in .env}"

WEBHOOK_BASE_URL="${WEBHOOK_BASE_URL_OVERRIDE:-https://${WEB_APP}.fly.dev}"
CORS_ORIGINS="${CORS_ORIGINS_OVERRIDE:-[\"https://${WEB_APP}.fly.dev\"]}"
SESSION_SECRET="${SESSION_SECRET:-$(openssl rand -hex 32)}"
ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-claude-sonnet-4-20250514}"

# Prefer an explicit Fly Redis URL; refuse localhost from local .env.
if [[ -n "${FLY_REDIS_URL:-}" ]]; then
  REDIS_URL="$FLY_REDIS_URL"
elif [[ -n "${REDIS_URL:-}" && "$REDIS_URL" != *"localhost"* && "$REDIS_URL" != *"127.0.0.1"* ]]; then
  :
else
  echo "REDIS_URL in .env looks local (or empty)."
  echo "Set a Fly/Upstash URL first, e.g.:"
  echo "  fly redis create --name ${API_APP}-redis --region iad"
  echo "  export FLY_REDIS_URL='redis://...'"
  echo "  $0"
  exit 1
fi

echo "==> Setting secrets on $API_APP (values not printed)"
"$FLY" secrets set --app "$API_APP" \
  "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}" \
  "ANTHROPIC_MODEL=${ANTHROPIC_MODEL}" \
  "ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY}" \
  "ELEVENLABS_AGENT_ID=${ELEVENLABS_AGENT_ID}" \
  "ELEVENLABS_AGENT_PHONE_NUMBER_ID=${ELEVENLABS_AGENT_PHONE_NUMBER_ID}" \
  "ELEVENLABS_WEBHOOK_SECRET=${ELEVENLABS_WEBHOOK_SECRET}" \
  "SESSION_SECRET=${SESSION_SECRET}" \
  "ADMIN_USERNAME=${ADMIN_USERNAME}" \
  "ADMIN_PASSWORD=${ADMIN_PASSWORD}" \
  "REDIS_URL=${REDIS_URL}" \
  "WEBHOOK_BASE_URL=${WEBHOOK_BASE_URL}" \
  "CORS_ORIGINS=${CORS_ORIGINS}" \
  "ALLOW_INSECURE_WEBHOOKS=false" \
  "SESSION_COOKIE_SECURE=true"

echo "==> Done. Current secret names:"
"$FLY" secrets list --app "$API_APP"
echo
echo "Point ElevenLabs post-call webhook at:"
echo "  ${WEBHOOK_BASE_URL}/api/webhooks/elevenlabs"
