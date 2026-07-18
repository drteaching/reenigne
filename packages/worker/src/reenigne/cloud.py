"""Cloud API client — transcribe & analyze without local provider keys."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, List

import httpx

from .models.transcript import TranscriptSegment


class CloudAPIError(RuntimeError):
    """Raised when the reenigne cloud API rejects a request."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class CloudClient:
    def __init__(self, base_url: str, token: str, timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def get_entitlements(self) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{self.base_url}/v1/me",
                headers=self._headers(),
            )
        if resp.status_code == 401:
            raise CloudAPIError("Invalid or expired token. Sign in again.", 401)
        if resp.status_code == 402:
            raise CloudAPIError(
                "Active subscription required. Visit https://reenigne.dev/pricing",
                402,
            )
        if resp.status_code >= 400:
            raise CloudAPIError(resp.text or resp.reason_phrase, resp.status_code)
        return resp.json()

    def require_active_subscription(self) -> dict[str, Any]:
        me = self.get_entitlements()
        status = me.get("subscription_status", "none")
        if status not in ("active", "trialing"):
            raise CloudAPIError(
                "Active subscription required to use cloud AI features. "
                "Visit https://reenigne.dev/pricing",
                402,
            )
        return me

    def transcribe(self, audio_path: Path) -> List[TranscriptSegment]:
        self.require_active_subscription()
        with open(audio_path, "rb") as f:
            files = {"file": (audio_path.name, f, "audio/wav")}
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/v1/transcribe",
                    headers=self._headers(),
                    files=files,
                )
        if resp.status_code == 402:
            raise CloudAPIError("Active subscription required.", 402)
        if resp.status_code >= 400:
            raise CloudAPIError(resp.text or "Transcription failed", resp.status_code)
        data = resp.json()
        return [
            TranscriptSegment(
                start=float(s["start"]),
                end=float(s["end"]),
                text=s["text"],
            )
            for s in data.get("segments", [])
        ]

    def analyze(
        self,
        *,
        target: str,
        duration_seconds: float,
        prompt_template: str,
        model: str,
        frames: List[dict[str, Any]],
    ) -> tuple[str, dict]:
        """
        frames: list of {index, timestamp_seconds, narration, ocr_text, image_b64}
        """
        self.require_active_subscription()
        payload = {
            "target": target,
            "duration_seconds": duration_seconds,
            "prompt_template": prompt_template,
            "model": model,
            "frames": frames,
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/v1/analyze",
                headers={**self._headers(), "Content-Type": "application/json"},
                content=json.dumps(payload),
            )
        if resp.status_code == 402:
            raise CloudAPIError("Active subscription required.", 402)
        if resp.status_code >= 400:
            raise CloudAPIError(resp.text or "Analysis failed", resp.status_code)
        data = resp.json()
        return data.get("markdown", ""), data.get("features") or {}


def encode_frame_image(
    path: Path,
    max_dimension: int = 1280,
    jpeg_quality: int = 80,
) -> tuple[str, str]:
    """
    Encode a screenshot for upload as (base64, media_type).

    Full-resolution PNGs are far too large to send — a single 4K frame is
    several MB, and a session sends dozens. Downscaling to `max_dimension` and
    re-encoding as JPEG cuts the payload by roughly 20x with no meaningful loss
    of detail at the resolution vision models actually sample. The originals
    stay on disk untouched for the HTML report.
    """
    try:
        import io

        from PIL import Image
    except ImportError:
        # No Pillow — send the original bytes rather than failing outright.
        return base64.standard_b64encode(path.read_bytes()).decode("utf-8"), "image/png"

    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)

    return base64.standard_b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"
