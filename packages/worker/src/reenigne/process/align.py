"""Align transcript segments to nearest frames by timestamp."""

from __future__ import annotations

from typing import List

from ..models.frame import Frame
from ..models.transcript import TranscriptSegment


def align_transcript_to_frames(
    frames: List[Frame],
    segments: List[TranscriptSegment],
) -> List[Frame]:
    """
    Attach narration text to each frame based on temporal overlap.
    A segment attaches to a frame if the segment's midpoint falls within
    the frame's window [ts, ts + interval).
    """
    if not frames:
        return frames

    # Compute frame windows
    interval = (frames[1].timestamp_seconds - frames[0].timestamp_seconds) if len(frames) > 1 else 3.0

    for frame in frames:
        window_start = frame.timestamp_seconds
        window_end = window_start + interval
        matching = []
        for seg in segments:
            midpoint = (seg.start + seg.end) / 2
            if window_start <= midpoint < window_end:
                matching.append(seg.text)
        if matching:
            frame.narration = " ".join(matching)

    return frames
