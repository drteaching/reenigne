"""OCR for extracting text visible in screenshots."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

# Tesseract is a system binary, not a pip dependency, so it is routinely
# missing. Warn once rather than silently returning empty text for every
# frame of every session.
_warned = False


def _warn_once(message: str) -> None:
    global _warned
    if not _warned:
        _warned = True
        print(f"[ocr] WARNING: {message} Continuing without OCR text.")


@lru_cache(maxsize=1)
def ocr_available() -> bool:
    """
    True if both pytesseract and the tesseract binary are usable.

    Cached — probing the binary spawns a subprocess, and this is called once
    per frame.
    """
    try:
        import pytesseract
    except ImportError:
        _warn_once("pytesseract is not installed.")
        return False
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        _warn_once(
            "the tesseract binary was not found on PATH "
            "(macOS: brew install tesseract, Windows: winget install "
            "UB-Mannheim.TesseractOCR, Linux: apt-get install tesseract-ocr)."
        )
        return False
    return True


def ocr_frame(image_path: Path) -> Optional[str]:
    """Return concatenated OCR text from a frame, or None if unavailable."""
    if not ocr_available():
        return None
    try:
        import pytesseract
        from PIL import Image

        with Image.open(image_path) as img:
            text = pytesseract.image_to_string(img)
    except Exception as e:
        print(f"[ocr] Failed on {image_path.name}: {e}")
        return None

    # Truncate crazy-long OCR output
    text = " ".join(text.split())
    return text[:1000] if text else None
