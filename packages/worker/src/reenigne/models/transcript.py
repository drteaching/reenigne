"""Transcript segment model."""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class TranscriptSegment:
    """A single transcribed segment of audio."""

    start: float  # seconds
    end: float    # seconds
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TranscriptSegment":
        return cls(**d)
