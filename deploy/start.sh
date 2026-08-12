#!/bin/sh
set -eu

# Prefer REDIS_URL from Fly secrets (e.g. Upstash). Otherwise start a local Redis.
case "${REDIS_URL:-}" in
  ""|redis://127.0.0.1:6379/0|redis://localhost:6379/0)
    redis-server --daemonize yes --save "" --appendonly no --bind 127.0.0.1
    export REDIS_URL="redis://127.0.0.1:6379/0"
    ;;
esac

# Open Fly's internal_port immediately (TCP must succeed during cold start).
nginx
# nginx masters daemonize by default; confirm 8080 is up.
i=0
while [ "$i" -lt 20 ]; do
  if wget -q -O /dev/null http://127.0.0.1:8080/ 2>/dev/null; then
    break
  fi
  i=$((i + 1))
  sleep 0.1
done

# API on loopback; nginx proxies /api → :8000
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

cleanup() {
  kill "$API_PID" 2>/dev/null || true
  nginx -s quit 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Block forever while API runs (replace with a wait that exits if API dies).
wait "$API_PID"
exit_code=$?
cleanup
trap - EXIT INT TERM
exit "$exit_code"
