"""ffmpeg detection and platform-specific command construction."""

from __future__ import annotations

import platform
import shutil
import subprocess
from typing import List


def find_ffmpeg() -> str:
    """Locate ffmpeg binary. Raises if not found."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install it:\n"
            "  macOS:   brew install ffmpeg\n"
            "  Windows: winget install ffmpeg  (or scoop install ffmpeg)\n"
            "  Linux:   apt-get install ffmpeg  (or your distro's package)"
        )
    return ffmpeg


def get_platform_capture_args(
    video_fps: int = 15,
    display: int | None = None,
) -> tuple[List[str], List[str]]:
    """
    Return (video_input_args, audio_input_args) for the current OS.

    macOS:   avfoundation
    Windows: gdigrab + dshow
    Linux:   x11grab + pulse
    """
    system = platform.system()

    if system == "Darwin":
        # macOS avfoundation. "1:0" typically means display 1, mic 0.
        disp = display if display is not None else 1
        video = [
            "-f", "avfoundation",
            "-framerate", str(video_fps),
            "-capture_cursor", "1",
            "-i", f"{disp}:0",  # video:audio device index
        ]
        audio = []  # combined with video in avfoundation
        return video, audio

    if system == "Windows":
        video = [
            "-f", "gdigrab",
            "-framerate", str(video_fps),
            "-i", "desktop",
        ]
        audio = [
            "-f", "dshow",
            "-i", "audio=default",  # user may override
        ]
        return video, audio

    if system == "Linux":
        # X11
        display = ":0.0"
        video = [
            "-f", "x11grab",
            "-framerate", str(video_fps),
            "-i", display,
        ]
        audio = [
            "-f", "pulse",
            "-i", "default",
        ]
        return video, audio

    raise RuntimeError(f"Unsupported platform: {system}")


def probe_media_duration(path) -> float | None:
    """
    Actual duration of a recorded file, in seconds, via ffprobe.

    Wall-clock timing is not a substitute: ffmpeg takes a variable moment to
    initialise capture devices and may drop frames under load, so wall-clock
    consistently overstates the media length. Frame timestamps and Whisper
    segments are both derived from the media itself, so the duration must be
    too or narration drifts out of sync with the screenshots.
    """
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    try:
        out = subprocess.check_output(
            [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
            timeout=30,
        )
        return float(out.strip())
    except (subprocess.SubprocessError, ValueError):
        return None


def get_display_resolution() -> str:
    """Best-effort detection of primary display resolution."""
    system = platform.system()
    try:
        if system == "Darwin":
            out = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType"], text=True, timeout=5
            )
            for line in out.splitlines():
                if "Resolution" in line:
                    return line.split(":", 1)[1].strip()
        elif system == "Linux":
            out = subprocess.check_output(["xdpyinfo"], text=True, timeout=5)
            for line in out.splitlines():
                if "dimensions:" in line:
                    return line.split(":", 1)[1].strip().split()[0]
        elif system == "Windows":
            out = subprocess.check_output(
                ["wmic", "path", "Win32_VideoController", "get", "CurrentHorizontalResolution,CurrentVerticalResolution"],
                text=True, timeout=5,
            )
            lines = [line.strip() for line in out.splitlines() if line.strip()]
            if len(lines) >= 2:
                return lines[1].replace("  ", "x")
    except Exception:
        pass
    return "unknown"
