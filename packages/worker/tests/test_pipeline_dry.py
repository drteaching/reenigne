"""Smoke test: manifest round-trip and alignment work without ffmpeg/APIs."""

from pathlib import Path
import tempfile

from reenigne.models.session import Session, save_manifest, load_manifest
from reenigne.models.frame import Frame
from reenigne.models.transcript import TranscriptSegment
from reenigne.process.align import align_transcript_to_frames


def test_manifest_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        s = Session(
            target="TestApp",
            duration_seconds=12.0,
            frame_interval_seconds=3.0,
        )
        s.frames = [
            Frame(
                index=1,
                path="screenshots/frame_000001.png",
                timestamp_seconds=0.0,
            ),
            Frame(
                index=2,
                path="screenshots/frame_000002.png",
                timestamp_seconds=3.0,
            ),
        ]
        s.transcript_segments = [
            TranscriptSegment(start=0.5, end=2.5, text="Login screen."),
            TranscriptSegment(start=3.5, end=5.5, text="Dashboard opens."),
        ]
        save_manifest(s, d)
        assert (d / "manifest.json").exists()

        loaded = load_manifest(d)
        assert loaded.target == "TestApp"
        assert len(loaded.frames) == 2
        assert loaded.transcript_segments[1].text == "Dashboard opens."


def test_alignment():
    frames = [
        Frame(index=1, path="a.png", timestamp_seconds=0.0),
        Frame(index=2, path="b.png", timestamp_seconds=3.0),
        Frame(index=3, path="c.png", timestamp_seconds=6.0),
    ]
    segments = [
        TranscriptSegment(start=0.5, end=2.5, text="First thing."),
        TranscriptSegment(start=3.1, end=4.0, text="Second thing."),
        TranscriptSegment(start=6.5, end=7.9, text="Third thing."),
    ]
    aligned = align_transcript_to_frames(frames, segments)
    assert aligned[0].narration == "First thing."
    assert aligned[1].narration == "Second thing."
    assert aligned[2].narration == "Third thing."


if __name__ == "__main__":
    test_manifest_roundtrip()
    test_alignment()
    print("All smoke tests passed.")
