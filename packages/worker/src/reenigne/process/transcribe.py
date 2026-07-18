"""OpenAI Whisper API transcription."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from ..capture.ffmpeg_utils import find_ffmpeg
from ..models.transcript import TranscriptSegment


def extract_audio(video_path: Path, output_wav: Path) -> Path:
    """Extract mono 16kHz WAV from video for Whisper."""
    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_wav),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_wav


def transcribe_audio(
    audio_path: Path,
    api_key: str,
    model: str = "whisper-1",
) -> List[TranscriptSegment]:
    """
    Transcribe audio via OpenAI Whisper API.
    Returns a list of TranscriptSegment objects with timestamps.
    """
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    print(f"[transcribe] Sending {audio_path.name} to Whisper API...")

    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model=model,
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    segments: List[TranscriptSegment] = []
    for seg in response.segments or []:
        # openai SDK returns objects; access attributes
        segments.append(
            TranscriptSegment(
                start=float(seg.start),
                end=float(seg.end),
                text=seg.text.strip(),
            )
        )

    print(f"[transcribe] Got {len(segments)} segments "
          f"(total {sum(s.duration for s in segments):.1f}s of speech)")
    return segments
