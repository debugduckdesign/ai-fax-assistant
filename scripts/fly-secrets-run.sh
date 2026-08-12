#!/usr/bin/env bash
# Interactive: login to Fly, resolve Redis URL, push secrets from .env
set -euo pipefail

export PATH="$HOME/.fly/bin:$PATH"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Fly login (browser will open if needed)"
fly auth login

echo
echo "==> Redis"
fly redis list || true
echo
echo "If you do not have Redis yet, run in another tab:"
echo "  fly redis create --name ai-fax-assistant-api-redis --region iad"
echo
if fly secrets list --app ai-fax-assistant-api 2>/dev/null | grep -q 'REDIS_URL'; then
  echo "App already has a REDIS_URL secret."
  echo "Paste Fly Redis URL to refresh it, or press Enter to keep existing and skip Redis in this push."
  read -r -p "FLY_REDIS_URL (optional): " FLY_REDIS_URL || true
  if [[ -z "${FLY_REDIS_URL:-}" ]]; then
    # Pull other secrets but keep existing REDIS by reading it is impossible;
    # require URL for the script's validation. Offer keep-path via dummy skip.
    echo "Keeping existing REDIS_URL requires the URL for validation."
    read -r -p "Paste current Fly Redis URL: " FLY_REDIS_URL
  fi
else
  read -r -p "Paste Fly Redis URL: " FLY_REDIS_URL
fi

export FLY_REDIS_URL
./scripts/fly-secrets-from-env.sh
