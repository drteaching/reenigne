"""Cloud API client — transcribe & analyze without local provider keys."""

from __future__ import annotations

import base64
import json
import time
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

    def submit_analysis(
        self,
        *,
        target: str,
        duration_seconds: float,
        prompt_template: str,
        model: str,
        frames: List[dict[str, Any]],
    ) -> str:
        """
        Enqueue an analysis job and return its id.

        frames: list of {index, timestamp_seconds, narration, ocr_text,
        image_b64, media_type}
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
                f"{self.base_url}/v1/analyze/jobs",
                headers={**self._headers(), "Content-Type": "application/json"},
                content=json.dumps(payload),
            )
        if resp.status_code == 402:
            raise CloudAPIError("Active subscription required.", 402)
        if resp.status_code == 429:
            raise CloudAPIError(
                _detail(resp) or "Too many analyses in progress.", 429
            )
        if resp.status_code >= 400:
            raise CloudAPIError(_detail(resp) or "Analysis failed", resp.status_code)
        return resp.json()["job_id"]

    def get_analysis_job(self, job_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{self.base_url}/v1/analyze/jobs/{job_id}",
                headers=self._headers(),
            )
        if resp.status_code == 404:
            raise CloudAPIError(f"Job {job_id} not found", 404)
        if resp.status_code >= 400:
            raise CloudAPIError(_detail(resp) or "Job lookup failed", resp.status_code)
        return resp.json()

    def wait_for_analysis(
        self,
        job_id: str,
        *,
        poll_interval: float = 3.0,
        max_wait_seconds: float = 1800.0,
        on_progress=None,
    ) -> tuple[str, dict]:
        """
        Poll until the job reaches a terminal state.

        Raises CloudAPIError on failure or if `max_wait_seconds` elapses. The
        job keeps running server-side after a timeout here — the id remains
        valid, so a caller can resume polling later.
        """
        deadline = time.monotonic() + max_wait_seconds
        last_status = None

        while True:
            job = self.get_analysis_job(job_id)
            status = job.get("status")

            if status != last_status:
                last_status = status
                if on_progress:
                    on_progress(status, job)

            if status == "succeeded":
                return job.get("markdown", ""), job.get("features") or {}
            if status == "failed":
                raise CloudAPIError(
                    f"Analysis failed: {job.get('error', 'unknown error')}"
                )

            if time.monotonic() >= deadline:
                raise CloudAPIError(
                    f"Timed out after {max_wait_seconds:.0f}s waiting for analysis. "
                    f"The job is still running — check back with job id {job_id}.",
                )
            time.sleep(poll_interval)

    def analyze(
        self,
        *,
        target: str,
        duration_seconds: float,
        prompt_template: str,
        model: str,
        frames: List[dict[str, Any]],
        on_progress=None,
    ) -> tuple[str, dict]:
        """Submit an analysis and block until it finishes."""
        job_id = self.submit_analysis(
            target=target,
            duration_seconds=duration_seconds,
            prompt_template=prompt_template,
            model=model,
            frames=frames,
        )
        return self.wait_for_analysis(job_id, on_progress=on_progress)


    def submit_feedback(
        self,
        *,
        kind: str,
        title: str,
        description: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Send a bug report or improvement suggestion.

        Works signed-out too — the endpoint accepts anonymous submissions —
        so this does not check entitlements first.
        """
        payload = {
            "kind": kind,
            "title": title,
            "description": description,
            "context": context or {},
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self.base_url}/v1/feedback",
                headers=headers,
                content=json.dumps(payload),
            )
        if resp.status_code >= 400:
            raise CloudAPIError(_detail(resp) or "Feedback failed", resp.status_code)
        return resp.json()


def _detail(resp: "httpx.Response") -> str:
    """Pull FastAPI's {"detail": ...} out of an error body when present."""
    try:
        body = resp.json()
    except Exception:
        return resp.text
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return resp.text


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
