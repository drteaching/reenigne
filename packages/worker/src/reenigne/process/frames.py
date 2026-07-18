"""Extract PNG frames from a recording at fixed intervals + dedupe."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from ..models.frame import Frame
from ..capture.ffmpeg_utils import find_ffmpeg


def extract_frames(
    video_path: Path,
    output_dir: Path,
    interval_seconds: float = 3.0,
    dedupe: bool = True,
    phash_threshold: int = 5,
) -> List[Frame]:
    """
    Extract frames every `interval_seconds` from `video_path` into `output_dir`.
    Returns list of Frame objects (excluding duplicates if dedupe=True).
    """
    ffmpeg = find_ffmpeg()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Clear old frames
    for f in output_dir.glob("frame_*.png"):
        f.unlink()

    fps = 1.0 / interval_seconds
    pattern = str(output_dir / "frame_%06d.png")

    cmd = [
        ffmpeg,
        "-y",
        "-i", str(video_path),
        "-vf", f"fps={fps}",
        "-q:v", "2",
        pattern,
    ]

    print(f"[frames] Extracting one frame every {interval_seconds}s...")
    subprocess.run(cmd, check=True, capture_output=True)

    # Enumerate extracted frames
    frame_paths = sorted(output_dir.glob("frame_*.png"))
    frames: List[Frame] = []

    prev_hash = None
    kept = 0
    dropped = 0

    for i, fpath in enumerate(frame_paths):
        ts = i * interval_seconds
        rel_path = f"screenshots/{fpath.name}"
        frame = Frame(index=i + 1, path=rel_path, timestamp_seconds=ts)

        if dedupe:
            phash = _compute_phash(fpath)
            frame.phash = phash

            if prev_hash is not None and _hamming(phash, prev_hash) <= phash_threshold:
                frame.is_duplicate = True
                fpath.unlink()  # remove duplicate from disk
                dropped += 1
                continue

            prev_hash = phash

        frames.append(frame)
        kept += 1

    print(f"[frames] Kept {kept} frames, dropped {dropped} duplicates.")
    return frames


def _compute_phash(image_path: Path) -> str:
    """Perceptual hash of an image, returned as hex string."""
    try:
        import imagehash
        from PIL import Image
        return str(imagehash.phash(Image.open(image_path)))
    except ImportError:
        # Fall back to file size hash — very crude
        return f"size_{image_path.stat().st_size}"


def _hamming(hash1: str, hash2: str) -> int:
    """Hamming distance between two hex hash strings."""
    if hash1.startswith("size_") or hash2.startswith("size_"):
        return 0 if hash1 == hash2 else 999
    try:
        import imagehash
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        return h1 - h2
    except Exception:
        return 999
