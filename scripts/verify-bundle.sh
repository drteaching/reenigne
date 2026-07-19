#!/usr/bin/env bash
#
# Verify a packaged macOS .app before it goes anywhere.
#
# Two failure modes this exists to catch, both of which produce an app that
# launches fine and then fails in front of a user:
#
#   1. A helper binary is missing. ffmpeg, ffprobe and the worker live in
#      extraResources; electron-builder will happily package an app without
#      them and the first recording dies.
#
#   2. A helper binary is signed with a different identity than the app —
#      including ad-hoc (the "-" identifier that codesign applies by default).
#      Under hardened runtime macOS then attributes the screen-recording TCC
#      request to that bare helper instead of to reenigne, which is the
#      confusing dialog the whole packaging setup exists to avoid. A bare
#      "is it signed?" check passes this case, so we compare Team IDs.
#
# Usage: verify-bundle.sh [path-to-.app]
# Exits nonzero on any missing or mismatched component.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${1:-}"

if [ -z "$APP" ]; then
  APP="$(find "$ROOT/apps/desktop/release" -maxdepth 2 -name '*.app' -print -quit 2>/dev/null || true)"
fi

if [ -z "$APP" ] || [ ! -d "$APP" ]; then
  echo "ERROR: no .app found. Pass one explicitly: verify-bundle.sh path/to/reenigne.app" >&2
  exit 1
fi

echo "Verifying $APP"

fail=0
note_fail() {
  echo "  FAIL: $1" >&2
  fail=1
}

RES="$APP/Contents/Resources"
REQUIRED=(
  "$RES/ffmpeg/ffmpeg"
  "$RES/ffmpeg/ffprobe"
  "$RES/worker/reenigne-worker"
)

# ---------------------------------------------------------------------------
# Presence and executability
# ---------------------------------------------------------------------------
echo "Contents:"
for path in "${REQUIRED[@]}"; do
  if [ ! -f "$path" ]; then
    note_fail "missing ${path#"$APP/"}"
    continue
  fi
  if [ ! -x "$path" ]; then
    note_fail "not executable: ${path#"$APP/"}"
    continue
  fi
  echo "  ok: ${path#"$APP/"}"
done

# ---------------------------------------------------------------------------
# Signature identity
# ---------------------------------------------------------------------------
if ! command -v codesign >/dev/null 2>&1; then
  # Refuse rather than skip. Silently passing the signature check on a machine
  # without codesign would let an unsigned build through the exact gate that
  # exists to stop it.
  echo "ERROR: codesign not found. Signature verification cannot run here;" >&2
  echo "       this script must be run on macOS with the Xcode command line" >&2
  echo "       tools installed." >&2
  exit 1
fi

# Team ID from `codesign -dvv`, which prints "TeamIdentifier=ABCDE12345" or
# "TeamIdentifier=not set" for ad-hoc signatures.
team_id_of() {
  codesign -dvv "$1" 2>&1 | sed -n 's/^TeamIdentifier=//p' | head -1
}

APP_TEAM="$(team_id_of "$APP")"

if [ -z "$APP_TEAM" ] || [ "$APP_TEAM" = "not set" ]; then
  note_fail "the app itself is unsigned or ad-hoc signed (TeamIdentifier='${APP_TEAM:-none}'). Set CSC_LINK/CSC_KEY_PASSWORD and rebuild."
else
  echo "App Team ID: $APP_TEAM"
fi

echo "Signatures:"
for path in "${REQUIRED[@]}"; do
  [ -f "$path" ] || continue
  rel="${path#"$APP/"}"

  if ! codesign --verify --strict "$path" >/dev/null 2>&1; then
    note_fail "$rel is not validly signed"
    continue
  fi

  team="$(team_id_of "$path")"
  if [ -z "$team" ] || [ "$team" = "not set" ]; then
    note_fail "$rel is ad-hoc signed (no Team ID). macOS will attribute the recording prompt to it, not to reenigne. Add it to build.mac.binaries in package.json."
  elif [ "$team" != "$APP_TEAM" ]; then
    note_fail "$rel Team ID $team != app Team ID $APP_TEAM"
  else
    echo "  ok: $rel ($team)"
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "" >&2
  echo "Bundle verification FAILED. Do not distribute this build." >&2
  exit 1
fi

echo ""
echo "Bundle verification passed."
