#!/usr/bin/env bash
# Copy Gold parquets into demo-data/ for Docker (Render) and GitHub.
# Usage: ./scripts/prepare_demo_data.sh [town_slug ...]
# Default town: arlington-ma (from SUPPORTED_TOWNS or first arg).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_ROOT="${ROOT}/data/gold"
DEST_ROOT="${ROOT}/demo-data/gold"

TOWNS=("${@}")
if [[ ${#TOWNS[@]} -eq 0 ]]; then
  TOWNS=(arlington-ma)
fi

mkdir -p "${DEST_ROOT}"

for town in "${TOWNS[@]}"; do
  src="${SRC_ROOT}/${town}"
  dest="${DEST_ROOT}/${town}"

  if [[ ! -d "${src}" ]]; then
    echo "ERROR: missing source gold data: ${src}" >&2
    echo "Run scrapers or copy parquets into data/gold/${town}/ first." >&2
    exit 1
  fi

  count="$(find "${src}" -maxdepth 1 -name '*.parquet' | wc -l | tr -d ' ')"
  if [[ "${count}" -eq 0 ]]; then
    echo "ERROR: no *.parquet files in ${src}" >&2
    exit 1
  fi

  rm -rf "${dest}"
  mkdir -p "${dest}"
  cp -a "${src}"/*.parquet "${dest}/"

  bytes="$(du -sb "${dest}" | cut -f1)"
  echo "OK: ${town} — ${count} parquet file(s), $(numfmt --to=iec-i --suffix=B "${bytes}" 2>/dev/null || echo "${bytes} bytes") → demo-data/gold/${town}/"
done

echo "Done. Commit demo-data/ and push to trigger Render rebuild."
