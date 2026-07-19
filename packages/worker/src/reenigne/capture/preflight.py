"""
Capture preflight: can we actually record on this machine, right now?

Three failures are indistinguishable from a stack trace and have completely
different fixes:

  - ffmpeg is not in the app bundle          -> reinstall
  - macOS refused the TCC request            -> grant in System Settings
  - something else broke                     -> report it

The UI renders the result of this directly, so it returns a stable structure
rather than raising, and every failure carries a message that names the fix.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from typing import Any

from .ffmpeg_utils import get_platform_capture_args

REASON_FFMPEG_MISSING = "ffmpeg_missing"
REASON_PERMISSION_DENIED = "permission_denied"
REASON_OTHER = "other"

# Substrings that indicate macOS refused the capture rather than ffmpeg
# failing on its own terms.
#
# NOT VERIFIED against a live TCC denial. These are the shapes avfoundation
# and ffmpeg are known to emit when access is refused; the exact string
# depends on macOS version and on which of screen or microphone was denied.
# docs/desktop-first-run-checklist.md has a step to capture the real output on
# a machine with permission revoked and add it here — this list is meant to be
# extended by one line.
#
# Anything not matched falls through to REASON_OTHER on purpose. Mislabelling
# an unrelated failure as a permission problem sends someone to System
# Settings to fix something that is not broken, which is worse than saying
# "unknown".
FAILURE_PATTERNS = (
    "failed to create avcapturedevice",
    "not authorized",
    "operation not permitted",
    "input/output error",
    "abort() called",
    "permission denied",
)


def classify_capture_error(stderr: str) -> str:
    """Map ffmpeg's stderr to a reason code."""
    haystack = (stderr or "").lower()
    if any(p in haystack for p in FAILURE_PATTERNS):
        return REASON_PERMISSION_DENIED
    return REASON_OTHER


def _message_for(reason: str) -> str:
    if reason == REASON_FFMPEG_MISSING:
        return (
            "The bundled ffmpeg is missing, so reenigne cannot record. "
            "Reinstall the app — this is a packaging problem, not a "
            "permission you can grant."
        )
    if reason == REASON_PERMISSION_DENIED:
        if platform.system() == "Darwin":
            return (
                "macOS refused the capture. Open System Settings › Privacy & "
                "Security and enable Screen & System Audio Recording and "
                "Microphone for reenigne, then restart the app — macOS only "
                "applies a screen-recording grant after a relaunch."
            )
        return (
            "The system refused the capture. Grant screen and microphone "
            "access to reenigne, then restart the app."
        )
    return (
        "Recording failed for a reason reenigne did not recognise. The "
        "details below are worth sending with a bug report."
    )


def _error(reason: str, detail: str = "") -> dict[str, str]:
    return {"reason": reason, "message": _message_for(reason), "detail": detail}


def _probe_capture(ffmpeg: str, seconds: int = 1) -> tuple[bool, str]:
    """
    Attempt a short real capture. Returns (ok, stderr).

    This is deliberately a real capture: on macOS there is no API to query or
    request screen-recording access, so provoking the system prompt requires
    actually trying to record. One second is enough to trigger TCC and short
    enough that a user pressing "Test permissions" is not left waiting.
    """
    video_args, audio_args = get_platform_capture_args(video_fps=5)
    out = os.path.join(tempfile.gettempdir(), "reenigne-preflight.mp4")

    cmd = [ffmpeg, "-y", *video_args, *audio_args, "-t", str(seconds), out]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=25)
    except subprocess.TimeoutExpired:
        return False, "ffmpeg timed out during the preflight capture"
    except OSError as e:
        return False, f"could not run ffmpeg: {e}"
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass

    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
    return proc.returncode == 0, stderr


def preflight() -> dict[str, Any]:
    """
    Check whether recording will work, and say precisely why if it will not.

    Returns {ffmpeg_found, ffmpeg_path, screen_ok, mic_ok, errors[]}. The shape
    is identical on every path so the UI can render it without branching on
    presence.

    Screen and microphone are reported separately, but a single capture
    exercises both on macOS: avfoundation takes them as one input. A denial of
    either fails the same call, so both are marked false and the message
    covers both rather than guessing which one was refused.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return {
            "ffmpeg_found": False,
            "ffmpeg_path": None,
            "screen_ok": False,
            "mic_ok": False,
            "errors": [_error(REASON_FFMPEG_MISSING)],
        }

    ok, stderr = _probe_capture(ffmpeg)
    if ok:
        return {
            "ffmpeg_found": True,
            "ffmpeg_path": ffmpeg,
            "screen_ok": True,
            "mic_ok": True,
            "errors": [],
        }

    reason = classify_capture_error(stderr)
    return {
        "ffmpeg_found": True,
        "ffmpeg_path": ffmpeg,
        "screen_ok": False,
        "mic_ok": False,
        "errors": [_error(reason, stderr.strip()[-2000:])],
    }
