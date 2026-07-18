"""Frame data model."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Frame:
    """A single captured screenshot with metadata."""

    index: int
    path: str  # relative to session dir
    timestamp_seconds: float
    phash: Optional[str] = None
    ocr_text: Optional[str] = None
    narration: Optional[str] = None
    is_duplicate: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Frame":
        return cls(**d)
