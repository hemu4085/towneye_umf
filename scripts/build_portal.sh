#!/usr/bin/env bash
# Build the TownEye portal frontend for production (towneye.ai).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"

if [[ ! -d node_modules ]]; then
  npm install
fi

npm run build
echo "Built → frontend/dist (serve via ./scripts/start_portal_prod.sh)"
