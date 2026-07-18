#!/usr/bin/env bash
# Build signed-ready desktop installers (mac universal + win x64).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

"$ROOT/scripts/build-worker.sh"

cd "$ROOT/apps/desktop"
npm ci
npm run build

case "${1:-all}" in
  mac)
    npm run dist:mac
    ;;
  win)
    npm run dist:win
    ;;
  all)
    npm run dist:mac
    npm run dist:win
    ;;
  *)
    echo "Usage: $0 [mac|win|all]"
    exit 1
    ;;
esac

echo "Artifacts in apps/desktop/release/"
echo "Code signing: set CSC_LINK / APPLE_ID / APPLE_APP_SPECIFIC_PASSWORD for notarization."
