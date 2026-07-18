"""Session model — the top-level entity."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .frame import Frame
from .transcript import TranscriptSegment


@dataclass
class Session:
    """Represents one recording session."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target: str = "unknown"
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    duration_seconds: float = 0.0
    display_resolution: str = ""
    frame_interval_seconds: float = 3.0
    frames: List[Frame] = field(default_factory=list)
    transcript_segments: List[TranscriptSegment] = field(default_factory=list)
    session_dir: Optional[Path] = None  # not serialized

    def to_manifest(self) -> dict:
        return {
            "session_id": self.session_id,
            "target": self.target,
            "started_at": self.started_at,
            "duration_seconds": self.duration_seconds,
            "display_resolution": self.display_resolution,
            "frame_interval_seconds": self.frame_interval_seconds,
            "frames": [f.to_dict() for f in self.frames],
            "transcript_segments": [s.to_dict() for s in self.transcript_segments],
        }

    @classmethod
    def from_manifest(cls, d: dict) -> "Session":
        return cls(
            session_id=d["session_id"],
            target=d.get("target", "unknown"),
            started_at=d["started_at"],
            duration_seconds=d.get("duration_seconds", 0.0),
            display_resolution=d.get("display_resolution", ""),
            frame_interval_seconds=d.get("frame_interval_seconds", 3.0),
            frames=[Frame.from_dict(f) for f in d.get("frames", [])],
            transcript_segments=[
                TranscriptSegment.from_dict(s) for s in d.get("transcript_segments", [])
            ],
        )


def save_manifest(session: Session, session_dir: Path) -> Path:
    """Write manifest.json to disk."""
    manifest_path = session_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(session.to_manifest(), f, indent=2, ensure_ascii=False)
    return manifest_path


def load_manifest(session_dir: Path) -> Session:
    """Read manifest.json from disk."""
    manifest_path = session_dir / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    session = Session.from_manifest(data)
    session.session_dir = session_dir
    return session
