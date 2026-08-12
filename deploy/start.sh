#!/bin/sh
set -eu

# Sessions are ephemeral; persistent fax/DB data lives on the Fly volume at /data.
redis-server --daemonize yes --save "" --appendonly no --bind 127.0.0.1

uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

cleanup() {
  kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Fail fast if the API never becomes ready.
i=0
while [ "$i" -lt 30 ]; do
  if wget -q -O /dev/null http://127.0.0.1:8000/api/health 2>/dev/null; then
    break
  fi
  i=$((i + 1))
  sleep 1
done

if ! kill -0 "$API_PID" 2>/dev/null; then
  echo "API process exited during startup" >&2
  exit 1
fi

exec nginx -g "daemon off;"
