"""The upload payload must fit the serverless body limit, not 413."""

import tempfile
from pathlib import Path

import pytest

from reenigne.analyze.llm_client import _build_payload_within_budget
from reenigne.models.frame import Frame

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _session_with_frames(d: Path, count: int, size=(1400, 900)):
    """
    Incompressible noise, so encoded size scales with the ladder rung rather
    than collapsing to nothing. Kept modest — these run on every commit.
    """
    import os

    shots = d / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(count):
        name = f"frame_{i:06d}.png"
        img = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
        img.save(shots / name, format="PNG")
        frames.append(
            Frame(index=i + 1, path=f"screenshots/{name}", timestamp_seconds=i * 3.0)
        )
    return frames


def test_payload_fits_budget_for_large_session():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        frames = _session_with_frames(d, 12)
        payload, total = _build_payload_within_budget(frames, d, budget=1_500_000)
        assert total <= 1_500_000
        assert len(payload) > 0


def test_quality_degrades_before_frames_are_dropped():
    """A moderately oversized session should keep every frame."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        frames = _session_with_frames(d, 6)
        payload, total = _build_payload_within_budget(frames, d, budget=1_500_000)
        assert len(payload) == 6
        assert total <= 1_500_000


def test_frames_dropped_only_when_quality_floor_insufficient():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        frames = _session_with_frames(d, 12)
        payload, total = _build_payload_within_budget(frames, d, budget=150_000)
        assert total <= 150_000 * 1.5  # sampling is approximate
        assert 0 < len(payload) < 12


def test_missing_images_are_skipped():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        frames = _session_with_frames(d, 2)
        frames.append(Frame(index=99, path="screenshots/gone.png", timestamp_seconds=9.0))
        payload, _ = _build_payload_within_budget(frames, d)
        assert len(payload) == 2


def test_empty_session_returns_empty():
    with tempfile.TemporaryDirectory() as td:
        payload, total = _build_payload_within_budget([], Path(td))
        assert payload == []
        assert total == 0
