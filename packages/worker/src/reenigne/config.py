"""Configuration loading and defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@dataclass
class Config:
    """Runtime configuration for reenigne."""

    # Cloud API (preferred — keys never live in the client)
    api_base_url: str = "https://api.reenigne.dev"
    api_token: Optional[str] = None

    # Dev-only local provider keys (ignored when api_token is set)
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    xai_api_key: Optional[str] = None

    # Model defaults
    default_llm_model: str = "grok-4"
    whisper_model: str = "whisper-1"

    # Capture defaults
    frame_interval_seconds: float = 3.0
    audio_sample_rate: int = 16000
    video_fps: int = 15

    # Output
    output_root: Path = Path.home() / "reenigne"

    # Processing
    phash_similarity_threshold: int = 5
    enable_ocr: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            api_base_url=os.getenv(
                "REENIGNE_API_URL", "https://api.reenigne.dev"
            ).rstrip("/"),
            api_token=os.getenv("REENIGNE_API_TOKEN"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            xai_api_key=os.getenv("XAI_API_KEY"),
            default_llm_model=os.getenv("REENIGNE_DEFAULT_MODEL", "grok-4"),
            frame_interval_seconds=float(
                os.getenv("REENIGNE_FRAME_INTERVAL", "3.0")
            ),
            output_root=Path(
                os.getenv("REENIGNE_OUTPUT_DIR", str(Path.home() / "reenigne"))
            ).expanduser(),
            enable_ocr=os.getenv("REENIGNE_NO_OCR", "").lower()
            not in ("1", "true", "yes"),
        )
