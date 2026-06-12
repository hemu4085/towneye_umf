#!/usr/bin/env bash
# Verify the portal frontend builds (run before pushing to Vercel).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"

if [[ ! -d node_modules ]]; then
  npm install
fi

npm run build

if [[ ! -f dist/index.html ]]; then
  echo "ERROR: frontend/dist/index.html missing — Vercel will 404"
  exit 1
fi

echo "OK: frontend/dist ready ($(du -sh dist | cut -f1))"
