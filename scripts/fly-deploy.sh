#!/usr/bin/env bash
# One-shot Fly.io bootstrap + deploy for AI Fax Assistant.
# Prerequisites: flyctl installed and logged in (`fly auth login`).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API_APP="${API_APP:-ai-fax-assistant-api}"
WEB_APP="${WEB_APP:-ai-fax-assistant-web}"
REGION="${FLY_REGION:-iad}"

if ! command -v flyctl >/dev/null 2>&1 && ! command -v fly >/dev/null 2>&1; then
  echo "Install flyctl first: https://fly.io/docs/hands-on/install-flyctl/"
  exit 1
fi
FLY="$(command -v flyctl || command -v fly)"

echo "==> Ensuring apps exist ($API_APP, $WEB_APP) in $REGION"
$FLY apps create "$API_APP" --org personal 2>/dev/null || true
$FLY apps create "$WEB_APP" --org personal 2>/dev/null || true

if [[ "$API_APP" != "ai-fax-assistant-api" || "$WEB_APP" != "ai-fax-assistant-web" ]]; then
  echo "Using custom app names — update fly.api.toml / fly.web.toml app + API_UPSTREAM to match."
fi

echo "==> Creating volume fax_data on $API_APP (no-op if exists)"
$FLY volumes create fax_data --app "$API_APP" --region "$REGION" --size 1 --yes 2>/dev/null || true

if [[ -z "${SKIP_REDIS:-}" ]]; then
  echo "==> Redis: create once with:"
  echo "    fly redis create --name ${API_APP}-redis --region $REGION"
  echo "    fly redis status <redis-name>   # copy private URL"
  echo "    fly secrets set REDIS_URL='...' --app $API_APP"
fi

echo "==> Reminder: set API secrets before first real use:"
echo "    fly secrets set --app $API_APP \\"
echo "      ANTHROPIC_API_KEY=... ELEVENLABS_API_KEY=... \\"
echo "      ELEVENLABS_AGENT_ID=... ELEVENLABS_AGENT_PHONE_NUMBER_ID=... \\"
echo "      ELEVENLABS_WEBHOOK_SECRET=... SESSION_SECRET=... \\"
echo "      ADMIN_PASSWORD=... REDIS_URL=... \\"
echo "      WEBHOOK_BASE_URL=https://${WEB_APP}.fly.dev \\"
echo "      CORS_ORIGINS='[\"https://${WEB_APP}.fly.dev\"]'"

echo "==> Deploying API"
$FLY deploy --config fly.api.toml --remote-only

echo "==> Deploying web"
$FLY deploy --config fly.web.toml --remote-only

echo "==> Done"
echo "    UI:  https://${WEB_APP}.fly.dev"
echo "    API: https://${API_APP}.fly.dev/api/health"
echo "    Webhook: https://${WEB_APP}.fly.dev/api/webhooks/elevenlabs"
