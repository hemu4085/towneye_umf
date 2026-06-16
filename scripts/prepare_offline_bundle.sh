#!/usr/bin/env bash
# Full offline bundle from Linux/WSL (no PowerShell). Default output: /mnt/c/aiops
set -euo pipefail
ROOT="${1:-/mnt/c/aiops}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REQ_SRC="$REPO_ROOT/requirements.txt"
WHEELS_REL="wheels-wsl"
WHEELS_DIR="$ROOT/$WHEELS_REL"
DEST_REPO="$ROOT/towneye_umf"

if [[ ! -f "$REQ_SRC" ]]; then
  echo "requirements.txt not found at $REQ_SRC" >&2
  exit 1
fi
if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required (install with: sudo apt install rsync)" >&2
  exit 1
fi

mkdir -p "$ROOT" "$WHEELS_DIR" "$DEST_REPO"
echo "Repo:        $REPO_ROOT"
echo "Bundle root: $ROOT"
echo "Wheels dir:  $WHEELS_DIR"

echo "Mirroring repo -> $DEST_REPO ..."
rsync -a --delete \
  --exclude '.venv' --exclude 'venv' --exclude '__pycache__' \
  --exclude '.pytest_cache' --exclude '.mypy_cache' --exclude 'node_modules' --exclude '.ruff_cache' \
  "$REPO_ROOT/" "$DEST_REPO/"

cp -f "$REQ_SRC" "$ROOT/requirements.txt"

echo "Downloading wheels (python3 -m pip download) ..."
python3 -m pip install -q -U pip
python3 -m pip download -r "$ROOT/requirements.txt" -d "$WHEELS_DIR"

{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  echo 'here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"'
  echo "python3 -m pip install --no-index --find-links=\"\$here/$WHEELS_REL\" -r \"\$here/requirements.txt\""
} > "$ROOT/install_offline.sh"
chmod +x "$ROOT/install_offline.sh"

ps1_path="$ROOT/install_offline.ps1"
cat > "$ps1_path" <<'EOFPS'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
python -m pip install --no-index --find-links=$(Join-Path $here 'PLACEHOLDER_WHEELS') -r (Join-Path $here "requirements.txt")
EOFPS
sed -i "s/PLACEHOLDER_WHEELS/$WHEELS_REL/" "$ps1_path"

cat > "$ROOT/env.offline.example" << 'EOFENV'
# Copy to .env on the offline machine (fill values while you still have secrets handy).
# DATABASE_URL=postgresql://...   # optional; omit for HashLinker offline mode
# GEMINI_API_KEY=
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# TAVILY_API_KEY=
# TOWNEYE_LLM_MODEL=
EOFENV

echo "Done."
echo "  Offline WSL/Linux: bash $ROOT/install_offline.sh"
echo "  Repo copy:         $DEST_REPO"
