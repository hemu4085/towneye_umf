#!/usr/bin/env bash
# Start TownEye Portal (backend + frontend) from repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — add ANTHROPIC_API_KEY for LLM reports."
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "Installing frontend dependencies…"
  (cd frontend && npm install)
fi

echo "Starting API on :8000 and UI on :5173"
echo "Test address: 29 Walnut St, Arlington MA"
echo ""

.venv/bin/uvicorn backend.main:app --reload --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

(cd frontend && npm run dev)
