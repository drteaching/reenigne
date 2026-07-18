"""Controllable recorder for GUI (start/stop without Ctrl+C)."""

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


class ScreenRecorder:
    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._start: float = 0.0
        self._output: Optional[Path] = None

    @property
    def is_recording(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(
        self,
        output_path: Path,
        video_fps: int = 15,
        display: Optional[int] = None,
        verbose: bool = False,
    ) -> None:
        if self.is_recording:
            raise RuntimeError("Already recording")
        ffmpeg = find_ffmpeg()
        video_args, audio_args = get_platform_capture_args(
            video_fps=video_fps, display=display
        )
        cmd = [ffmpeg, "-y"]
        cmd.extend(video_args)
        if audio_args:
            cmd.extend(audio_args)
        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(output_path),
            ]
        )
        if verbose:
            print(f"[capture] Command: {' '.join(cmd)}", file=sys.stderr)
        self._output = output_path
        self._start = time.time()
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL if not verbose else None,
            stderr=subprocess.DEVNULL if not verbose else None,
        )
        print("[capture] Recording started (GUI mode).")

    def stop(self) -> float:
        if not self._proc:
            return 0.0
        try:
            if self._proc.stdin:
                self._proc.communicate(input=b"q", timeout=8)
            else:
                self._proc.terminate()
                self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=5)
        self._proc = None
        # Real media duration keeps narration aligned to frames; wall-clock
        # includes capture-device startup lag.
        duration = probe_media_duration(self._output) if self._output else None
        if duration is None:
            duration = time.time() - self._start
            print("[capture] WARNING: ffprobe unavailable; using wall-clock duration.")
        print(f"[capture] Recording saved: {self._output} ({duration:.1f}s)")
        return duration


# Module-level singleton for RPC worker process
ACTIVE_RECORDER = ScreenRecorder()
