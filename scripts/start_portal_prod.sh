#!/usr/bin/env bash
# Production demo server for https://towneye.ai — API + built frontend on one port.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env — review PORTAL_PUBLIC_URL and ANTHROPIC_API_KEY."
fi

"$ROOT/scripts/build_portal.sh"

export TOWNEYE_ENV=production
export SERVE_FRONTEND=true
export PORTAL_PUBLIC_URL="${PORTAL_PUBLIC_URL:-https://towneye.ai}"

HOST="${PORTAL_HOST:-0.0.0.0}"
PORT="${PORTAL_PORT:-8000}"

echo "TownEye demo → http://${HOST}:${PORT}"
echo "Public URL  → ${PORTAL_PUBLIC_URL}"
echo "Test address: 29 Walnut St, Arlington MA"
echo ""

exec .venv/bin/uvicorn backend.main:app --host "$HOST" --port "$PORT"
