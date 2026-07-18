"""Cross-platform screen + audio recording using ffmpeg."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .ffmpeg_utils import (
    find_ffmpeg,
    get_platform_capture_args,
    probe_media_duration,
)


def record_screen_and_audio(
    output_path: Path,
    video_fps: int = 15,
    verbose: bool = False,
    display: Optional[int] = None,
) -> float:
    """
    Record screen + microphone to an mp4 file.

    Blocks until user sends SIGINT (Ctrl+C). Returns duration in seconds.
    """
    ffmpeg = find_ffmpeg()
    video_args, audio_args = get_platform_capture_args(
        video_fps=video_fps, display=display
    )

    cmd = [ffmpeg, "-y"]  # overwrite
    cmd.extend(video_args)
    if audio_args:
        cmd.extend(audio_args)

    cmd.extend([
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        str(output_path),
    ])

    if verbose:
        print(f"[capture] Command: {' '.join(cmd)}", file=sys.stderr)

    print("[capture] Recording started. Press Ctrl+C to stop.")
    start = time.time()

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL if not verbose else None,
        stderr=subprocess.DEVNULL if not verbose else None,
    )

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[capture] Stopping recording gracefully...")
        # Send 'q' to ffmpeg for clean shutdown
        try:
            proc.communicate(input=b"q", timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)

    # Prefer the real media duration; wall-clock includes device startup lag
    # and would desync narration from frames.
    duration = probe_media_duration(output_path)
    if duration is None:
        duration = time.time() - start
        print("[capture] WARNING: ffprobe unavailable; using wall-clock duration.")
    print(f"[capture] Recording saved: {output_path} ({duration:.1f}s)")
    return duration
