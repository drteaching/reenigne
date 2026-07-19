#!/usr/bin/env bash
#
# Build desktop installers.
#
# ---------------------------------------------------------------------------
# Signing and notarisation — order matters
# ---------------------------------------------------------------------------
#
# On macOS the embedded ffmpeg, ffprobe and worker binaries MUST be signed
# with the same Developer ID as the app. They are listed in package.json under
# build.mac.binaries; electron-builder does not sign extraResources otherwise.
#
# This is not cosmetic. Under hardened runtime an unsigned — or ad-hoc signed —
# helper inside a Developer ID app makes macOS attribute the screen-recording
# TCC request to that bare helper rather than to "reenigne", which is the
# confusing dialog this whole setup exists to avoid. scripts/verify-bundle.sh
# checks Team IDs match, not merely that a signature exists.
#
# Environment, in the order electron-builder consumes it:
#
#   1. Signing identity (required for a distributable build)
#      CSC_LINK                    base64 .p12, or a file:// path to one
#      CSC_KEY_PASSWORD            password for that .p12
#      # Or, if the identity is already in the login keychain, omit both and
#      # electron-builder will find it.
#
#   2. Notarisation (required for Gatekeeper to accept it on another Mac)
#      APPLE_ID                    Apple ID email
#      APPLE_APP_SPECIFIC_PASSWORD app-specific password, not the account one
#      APPLE_TEAM_ID               10-character Team ID
#
#   3. Then, in order:
#      build-worker.sh             PyInstaller worker -> resources/worker
#      (manual)                    place ffmpeg + ffprobe in resources/ffmpeg
#      npm run dist:mac            package, sign app AND listed binaries
#      electron-builder            staples the notarisation ticket
#      scripts/verify-bundle.sh    confirm contents and Team ID agreement
#
# Without CSC_* the build still produces a .app, but unsigned: usable for
# local testing, not for distribution, and the TCC attribution will be wrong.
#
# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------
#
# The Windows target cannot be produced from macOS or Linux. build-worker.sh
# runs PyInstaller on the host, and --onefile does not cross-compile, so a
# Windows installer built here would contain a macOS worker binary — a broken
# artefact rather than a missing one. Building for Windows requires running
# this script on a Windows host. The guard below refuses rather than shipping
# something that cannot work.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

TARGET="${1:-all}"
HOST="$(uname -s)"

build_worker() {
  "$ROOT/scripts/build-worker.sh"
}

require_windows_host() {
  if [ "$HOST" != "MINGW"* ] && [ "$HOST" != "MSYS"* ] && [ "$HOST" != "CYGWIN"* ]; then
    cat >&2 <<'MSG'
ERROR: cannot build the Windows target from this host.

build-worker.sh runs PyInstaller on the host and --onefile cannot
cross-compile, so the installer would bundle a non-Windows worker binary and
fail at first launch. Run this script on a Windows machine to produce it.
MSG
    exit 1
  fi
}

cd "$ROOT/apps/desktop"

case "$TARGET" in
  mac)
    build_worker
    npm ci
    npm run build
    npm run dist:mac
    "$ROOT/scripts/verify-bundle.sh"
    ;;
  win)
    require_windows_host
    build_worker
    npm ci
    npm run build
    npm run dist:win
    ;;
  all)
    # Deliberately mac-only: see the Windows note above. Kept as a target so
    # existing invocations do not silently produce a broken .exe.
    echo "note: 'all' builds macOS only; Windows needs a Windows host." >&2
    build_worker
    npm ci
    npm run build
    npm run dist:mac
    "$ROOT/scripts/verify-bundle.sh"
    ;;
  *)
    echo "Usage: $0 [mac|win|all]" >&2
    exit 1
    ;;
esac

echo "Artifacts in apps/desktop/release/"
