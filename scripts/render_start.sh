#!/usr/bin/env bash
# Render start — install into Render's .venv, then launch uvicorn.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
PIP="$VENV/bin/pip"
PY="$VENV/bin/python"

if [[ ! -x "$PIP" ]]; then
  echo "Render .venv not found at $VENV — creating one"
  python -m venv "$VENV"
fi

REQ="$ROOT/requirements-portal.txt"
if [[ ! -f "$REQ" ]]; then
  REQ="$ROOT/requirements.txt"
fi

echo "Installing into $VENV from $REQ"
"$PIP" install --upgrade pip
"$PIP" install -r "$REQ"
"$PY" -c "import fastapi; print('fastapi OK:', fastapi.__version__)"

exec "$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
