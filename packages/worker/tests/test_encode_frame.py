"""Frames must be downscaled before upload — full-res PNGs blow the body limit."""

import base64
import io
import tempfile
from pathlib import Path

import pytest

from reenigne.cloud import encode_frame_image

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _write_png(path: Path, size=(2560, 1440)):
    # Noise, not flat colour — a flat image compresses to almost nothing and
    # would make the size comparison meaningless.
    import os

    img = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
    img.save(path, format="PNG")
    return path


def test_encode_returns_jpeg_media_type():
    with tempfile.TemporaryDirectory() as td:
        p = _write_png(Path(td) / "frame.png", size=(800, 600))
        _, media_type = encode_frame_image(p)
        assert media_type == "image/jpeg"


def test_large_frame_is_downscaled_within_bounds():
    with tempfile.TemporaryDirectory() as td:
        p = _write_png(Path(td) / "frame.png", size=(2560, 1440))
        b64, _ = encode_frame_image(p, max_dimension=1280)

        with Image.open(io.BytesIO(base64.standard_b64decode(b64))) as img:
            assert max(img.size) <= 1280
            # Aspect ratio preserved (16:9 → 1280x720)
            assert img.size == (1280, 720)


def test_encoded_payload_is_far_smaller_than_source():
    with tempfile.TemporaryDirectory() as td:
        p = _write_png(Path(td) / "frame.png", size=(2560, 1440))
        source_bytes = p.stat().st_size
        b64, _ = encode_frame_image(p)
        encoded_bytes = len(base64.standard_b64decode(b64))

        assert encoded_bytes < source_bytes / 10, (
            f"expected >10x reduction, got {source_bytes} -> {encoded_bytes}"
        )


def test_small_frame_is_not_upscaled():
    with tempfile.TemporaryDirectory() as td:
        p = _write_png(Path(td) / "frame.png", size=(640, 480))
        b64, _ = encode_frame_image(p, max_dimension=1280)
        with Image.open(io.BytesIO(base64.standard_b64decode(b64))) as img:
            assert img.size == (640, 480)
