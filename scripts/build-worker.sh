#!/usr/bin/env bash
# Bundle the Python worker with PyInstaller for Electron extraResources.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKER="$ROOT/packages/worker"
OUT_MAC="$ROOT/apps/desktop/resources/worker"
OUT_NAME="reenigne-worker"

# Canonical prompts (zero-dependency, lives with the server). The worker
# depends on `reenigne-prompts`, which is not published to PyPI, so install
# it from the repo before the worker itself.
python3 -m pip install -e "$ROOT/apps/api" -q

cd "$WORKER"
python3 -m pip install -e ".[dev]" -q
python3 -m PyInstaller \
  --onefile \
  --name "$OUT_NAME" \
  --paths src \
  --hidden-import reenigne \
  --hidden-import reenigne.worker_rpc \
  --hidden-import reenigne_prompts \
  --distpath "$OUT_MAC" \
  --workpath "$ROOT/.build/pyinstaller" \
  --specpath "$ROOT/.build/pyinstaller" \
  -y \
  src/reenigne/worker_rpc.py

echo "Worker binary: $OUT_MAC/$OUT_NAME"
echo "Place platform ffmpeg binaries in apps/desktop/resources/ffmpeg/"
