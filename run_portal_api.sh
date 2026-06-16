#!/usr/bin/env bash
# Render entrypoint — install deps into .venv, then start portal API.
# Start command on Render: bash run_portal_api.sh
set -ex

cd "${RENDER_PROJECT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
echo "Working directory: $(pwd)"
echo "Python: $(which python3 || true)"

if [[ ! -x .venv/bin/pip ]]; then
  python3 -m venv .venv
fi

PIP=".venv/bin/pip"
PY=".venv/bin/python"

"$PIP" install --upgrade pip

if [[ -f requirements-portal.txt ]]; then
  "$PIP" install -r requirements-portal.txt
elif [[ -f requirements.txt ]]; then
  "$PIP" install -r requirements.txt
else
  "$PIP" install fastapi "uvicorn[standard]" httpx python-dotenv email-validator \
    pydantic PyYAML pandas pyarrow shapely anthropic jinja2 duckdb geohash2 requests
fi

"$PY" -c "import fastapi; print('fastapi OK', fastapi.__version__)"

exec "$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
