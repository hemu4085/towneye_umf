#!/usr/bin/env bash
# Boot FastAPI (:8000) + Next.js MVP (:3000) from towneye-ai/
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

UVICORN=""
for candidate in \
  "$ROOT/.venv/bin/uvicorn" \
  "$ROOT/../towneye_umf/.venv/bin/uvicorn"; do
  if [[ -x "$candidate" ]]; then
    UVICORN="$candidate"
    break
  fi
done
if [[ -z "$UVICORN" ]] && command -v uvicorn >/dev/null 2>&1; then
  UVICORN="$(command -v uvicorn)"
fi
if [[ -z "$UVICORN" ]]; then
  echo "No uvicorn found. Activate a venv or create .venv in the repo root."
  exit 1
fi

echo "Clearing stale processes on :8000 and :3000…"
pkill -f 'uvicorn backend.main:app' 2>/dev/null || true
pkill -f 'next dev -H 0.0.0.0' 2>/dev/null || true
sleep 1

echo "Installing Next.js dependencies…"
(cd towneye-ai && npm install)

cleanup() {
  echo ""
  echo "Stopping servers…"
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup INT TERM

echo "Starting FastAPI Backend on :8000…"
"$UVICORN" backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

echo "Starting Next.js Frontend on :3000…"
(cd towneye-ai && npm run dev -- -H 0.0.0.0) &
FRONTEND_PID=$!

echo ""
echo "Both servers running. Press Ctrl+C to stop."
echo "  API:  http://localhost:8000/api/health"
echo "  UI:   http://localhost:3000"
echo ""

# wait exits non-zero if a child dies — do NOT use set -e here
wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
