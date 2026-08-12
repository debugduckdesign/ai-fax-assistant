#!/usr/bin/env bash
# One-shot Fly.io bootstrap + deploy for AI Fax Assistant (single app).
# Prerequisites: flyctl installed and logged in (`fly auth login`).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP="${APP:-ai-fax-assistant}"
REGION="${FLY_REGION:-ams}"

if ! command -v flyctl >/dev/null 2>&1 && ! command -v fly >/dev/null 2>&1; then
  echo "Install flyctl first: https://fly.io/docs/hands-on/install-flyctl/"
  exit 1
fi
FLY="$(command -v flyctl || command -v fly)"

echo "==> Ensuring app exists ($APP) in $REGION"
$FLY apps create "$APP" --org personal 2>/dev/null || true

echo "==> Creating volume fax_data on $APP (no-op if exists)"
$FLY volumes create fax_data --app "$APP" --region "$REGION" --size 1 --yes 2>/dev/null || true

echo "==> Reminder: set secrets before first real use:"
echo "    fly secrets set --app $APP \\"
echo "      ANTHROPIC_API_KEY=... ELEVENLABS_API_KEY=... \\"
echo "      ELEVENLABS_AGENT_ID=... ELEVENLABS_AGENT_PHONE_NUMBER_ID=... \\"
echo "      ELEVENLABS_WEBHOOK_SECRET=... SESSION_SECRET=... \\"
echo "      ADMIN_PASSWORD=... \\"
echo "      WEBHOOK_BASE_URL=https://${APP}.fly.dev \\"
echo "      CORS_ORIGINS='[\"https://${APP}.fly.dev\"]'"
echo "    # Optional: fly redis create … then fly secrets set REDIS_URL=…"

echo "==> Deploying"
$FLY deploy --config fly.toml --remote-only --ha=false

echo "==> Done"
echo "    UI:      https://${APP}.fly.dev"
echo "    Health:  https://${APP}.fly.dev/api/health"
echo "    Webhook: https://${APP}.fly.dev/api/webhooks/elevenlabs"
echo "    Note: Fly trial VMs stop after ~5m unless a payment method is on file."
