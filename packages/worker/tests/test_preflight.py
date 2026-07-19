"""
Capture preflight.

Three failures look identical from a stack trace and have completely
different fixes: ffmpeg is not in the bundle, macOS denied the TCC request,
or something else broke. Preflight has to tell them apart, because the
message the user sees is the only thing that decides whether they can
recover on their own.

The TCC denial patterns are a documented best guess, not an observed
recording — see FAILURE_PATTERNS in capture/preflight.py and the step in
docs/desktop-first-run-checklist.md that captures the real string. These
tests prove the classifier routes correctly; they do not prove the pattern
list is complete.
"""

import subprocess
from unittest.mock import patch

import pytest

from reenigne.capture.preflight import (
    REASON_FFMPEG_MISSING,
    REASON_OTHER,
    REASON_PERMISSION_DENIED,
    classify_capture_error,
    preflight,
)


# ---------- Classifier ----------


@pytest.mark.parametrize(
    "stderr",
    [
        "[AVFoundation indev @ 0x7f8] Failed to create AVCaptureDeviceInput",
        "abort() called, screen capture not authorized",
        "[avfoundation @ 0x600] Operation not permitted",
        "Input/output error opening 'Capture screen 0'",
        "This app is not authorized to use the microphone",
        "AVCaptureDevice was not authorized for use",
    ],
)
def test_permission_shaped_errors_are_classified_as_denied(stderr):
    assert classify_capture_error(stderr) == REASON_PERMISSION_DENIED


@pytest.mark.parametrize(
    "stderr",
    [
        "Invalid framerate value",
        "Unknown encoder 'libx264'",
        "No space left on device",
        "",
    ],
)
def test_unrecognised_errors_fall_through_to_other(stderr):
    """
    Never guess. Mislabelling an unrelated failure as a permission problem
    sends the user to System Settings to fix something that is not broken.
    """
    assert classify_capture_error(stderr) == REASON_OTHER


# ---------- Missing ffmpeg ----------


def test_missing_ffmpeg_is_reported_without_attempting_capture():
    with patch("reenigne.capture.preflight.shutil.which", return_value=None):
        with patch("reenigne.capture.preflight.subprocess.run") as run:
            result = preflight()

    assert result["ffmpeg_found"] is False
    assert result["screen_ok"] is False
    assert result["mic_ok"] is False
    assert run.call_count == 0, "should not try to capture without ffmpeg"

    assert result["errors"], "a failure must always carry an error"
    assert result["errors"][0]["reason"] == REASON_FFMPEG_MISSING
    # The message has to name the fix, not just the symptom.
    assert "reinstall" in result["errors"][0]["message"].lower()


def test_missing_ffmpeg_reports_no_path():
    with patch("reenigne.capture.preflight.shutil.which", return_value=None):
        assert preflight()["ffmpeg_path"] is None


# ---------- Permission denied ----------


def _denied(*a, **kw):
    return subprocess.CompletedProcess(
        args=a[0] if a else [],
        returncode=1,
        stdout=b"",
        stderr=b"[AVFoundation indev @ 0x7f8] Failed to create AVCaptureDeviceInput",
    )


def test_permission_denial_is_distinguished_from_missing_ffmpeg():
    with patch("reenigne.capture.preflight.shutil.which", return_value="/x/ffmpeg"):
        with patch("reenigne.capture.preflight.subprocess.run", side_effect=_denied):
            result = preflight()

    assert result["ffmpeg_found"] is True, "ffmpeg exists; only access was refused"
    assert result["screen_ok"] is False
    assert result["errors"][0]["reason"] == REASON_PERMISSION_DENIED
    assert "System Settings" in result["errors"][0]["message"]


def test_permission_denial_message_does_not_tell_the_user_to_reinstall():
    """Wrong fix for this failure; reinstalling changes nothing."""
    with patch("reenigne.capture.preflight.shutil.which", return_value="/x/ffmpeg"):
        with patch("reenigne.capture.preflight.subprocess.run", side_effect=_denied):
            message = preflight()["errors"][0]["message"].lower()
    assert "reinstall" not in message


# ---------- Other failures ----------


def test_unrelated_failure_is_reported_as_other():
    def _broken(*a, **kw):
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout=b"", stderr=b"Unknown encoder 'libx264'"
        )

    with patch("reenigne.capture.preflight.shutil.which", return_value="/x/ffmpeg"):
        with patch("reenigne.capture.preflight.subprocess.run", side_effect=_broken):
            result = preflight()

    err = result["errors"][0]
    assert err["reason"] == REASON_OTHER
    # The raw stderr is kept for a bug report, but not as the whole message.
    assert "libx264" in err["detail"]
    assert err["message"] != err["detail"]


def test_timeout_is_not_mistaken_for_a_denial():
    def _timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=15)

    with patch("reenigne.capture.preflight.shutil.which", return_value="/x/ffmpeg"):
        with patch("reenigne.capture.preflight.subprocess.run", side_effect=_timeout):
            result = preflight()

    assert result["screen_ok"] is False
    assert result["errors"][0]["reason"] == REASON_OTHER


# ---------- Success ----------


def _ok(*a, **kw):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")


def test_success_reports_everything_granted_and_no_errors():
    with patch("reenigne.capture.preflight.shutil.which", return_value="/x/ffmpeg"):
        with patch("reenigne.capture.preflight.subprocess.run", side_effect=_ok):
            result = preflight()

    assert result == {
        "ffmpeg_found": True,
        "ffmpeg_path": "/x/ffmpeg",
        "screen_ok": True,
        "mic_ok": True,
        "errors": [],
    }


def test_result_shape_is_stable_across_every_path():
    """The UI renders this dict directly; the keys must always be present."""
    keys = {"ffmpeg_found", "ffmpeg_path", "screen_ok", "mic_ok", "errors"}

    with patch("reenigne.capture.preflight.shutil.which", return_value=None):
        assert set(preflight()) == keys

    with patch("reenigne.capture.preflight.shutil.which", return_value="/x/ffmpeg"):
        with patch("reenigne.capture.preflight.subprocess.run", side_effect=_denied):
            assert set(preflight()) == keys
        with patch("reenigne.capture.preflight.subprocess.run", side_effect=_ok):
            assert set(preflight()) == keys


def test_capture_attempt_is_short_and_bounded():
    """A preflight that hangs is worse than one that fails."""
    captured = {}

    def _record(cmd, **kw):
        captured["cmd"] = cmd
        captured["timeout"] = kw.get("timeout")
        return _ok()

    with patch("reenigne.capture.preflight.shutil.which", return_value="/x/ffmpeg"):
        with patch("reenigne.capture.preflight.subprocess.run", side_effect=_record):
            preflight()

    assert captured["timeout"] is not None and captured["timeout"] <= 30
    assert "-t" in captured["cmd"], "capture must be time-limited"
