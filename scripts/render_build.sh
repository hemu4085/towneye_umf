#!/usr/bin/env bash
# Render build — install portal API deps into Render's .venv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
PIP="$VENV/bin/pip"
PY="$VENV/bin/python"

if [[ ! -x "$PIP" ]]; then
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
