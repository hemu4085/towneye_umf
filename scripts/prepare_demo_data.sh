#!/usr/bin/env bash
# Copy demo gold data into demo-data/ for Railway Docker builds (git-committable).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/data/gold/arlington-ma"
DEST="$ROOT/demo-data/gold/arlington-ma"

if [[ ! -d "$SRC" ]]; then
  echo "Missing $SRC — run scrapers locally first or copy gold data manually."
  exit 1
fi

mkdir -p "$DEST"
rsync -a --delete "$SRC/" "$DEST/"
echo "Demo data ready: $DEST ($(du -sh "$DEST" | cut -f1))"
