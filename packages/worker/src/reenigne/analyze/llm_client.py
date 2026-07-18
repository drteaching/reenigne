"""LLM analysis — cloud API primary; local providers for dev fallback only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

from ..cloud import CloudClient, encode_frame_image
from ..config import Config
from ..models.session import Session
from .prompts import PROMPTS


# Serverless platforms cap request bodies (Vercel: 4.5 MB). Leave headroom for
# JSON overhead, narration, and OCR text alongside the base64 image data.
CLOUD_PAYLOAD_BUDGET_BYTES = 3_500_000

# Tried in order until the payload fits. Vision models sample images at modest
# resolution, so the lower rungs cost far less quality than they save bytes.
_ENCODE_LADDER = [(1280, 80), (1024, 75), (896, 70), (768, 65)]


def _build_payload_within_budget(
    frames,
    session_dir: Path,
    budget: int = CLOUD_PAYLOAD_BUDGET_BYTES,
) -> tuple[list[dict], int]:
    """
    Encode frames to fit `budget` bytes of base64.

    Degrades image quality first, and only then drops frames — losing detail
    in every frame beats losing whole steps of the walkthrough. Returns
    (payload_frames, total_bytes).
    """
    usable = [f for f in frames if (session_dir / f.path).exists()]
    if not usable:
        return [], 0

    def encode(subset, max_dim, quality):
        out = []
        total = 0
        for f in subset:
            b64, media_type = encode_frame_image(
                session_dir / f.path, max_dimension=max_dim, jpeg_quality=quality
            )
            total += len(b64)
            out.append(
                {
                    "index": f.index,
                    "timestamp_seconds": f.timestamp_seconds,
                    "narration": f.narration or "",
                    "ocr_text": (f.ocr_text or "")[:200],
                    "image_b64": b64,
                    "media_type": media_type,
                }
            )
        return out, total

    for max_dim, quality in _ENCODE_LADDER:
        payload, total = encode(usable, max_dim, quality)
        if total <= budget:
            if (max_dim, quality) != _ENCODE_LADDER[0]:
                print(
                    f"[analyze] Reduced frame quality to {max_dim}px/q{quality} "
                    f"to fit the {budget / 1_000_000:.1f} MB upload limit."
                )
            return payload, total

    # Still over at the lowest quality — drop frames evenly, keeping the
    # walkthrough's shape by sampling across the whole session.
    max_dim, quality = _ENCODE_LADDER[-1]
    per_frame = total / len(usable)
    keep = max(1, int(budget / per_frame))
    step = len(usable) / keep
    subset = [usable[int(i * step)] for i in range(keep)]
    payload, total = encode(subset, max_dim, quality)
    print(
        f"[analyze] WARNING: session too large for the upload limit; "
        f"sending {len(payload)} of {len(usable)} frames "
        f"({total / 1_000_000:.1f} MB). Record shorter sessions or raise "
        f"--interval for better coverage."
    )
    return payload, total


def analyze_session(
    session: Session,
    session_dir: Path,
    model: str = "grok-4",
    prompt_template: str = "teardown",
    cfg: Optional[Config] = None,
    api_key: Optional[str] = None,
    max_frames: int = 30,
) -> tuple[str, dict]:
    """
    Send session bundle to an LLM. Returns (markdown_report, structured_json).
    Prefers reenigne cloud API when REENIGNE_API_TOKEN is set.
    """
    if prompt_template not in PROMPTS:
        raise ValueError(
            f"Unknown prompt template: {prompt_template}. "
            f"Available: {list(PROMPTS.keys())}"
        )

    cfg = cfg or Config.from_env()

    frames = [f for f in session.frames if not f.is_duplicate]
    if len(frames) > max_frames:
        step = len(frames) / max_frames
        frames = [frames[int(i * step)] for i in range(max_frames)]
        print(
            f"[analyze] Downsampled to {len(frames)} frames "
            f"(from {len(session.frames)}) to fit context."
        )

    if cfg.api_token:
        client = CloudClient(cfg.api_base_url, cfg.api_token)
        payload_frames, payload_bytes = _build_payload_within_budget(
            frames, session_dir
        )
        if not payload_frames:
            raise RuntimeError(
                "No screenshots available to analyze — the session directory "
                "has no readable frame images."
            )
        print(
            f"[analyze] Submitting to reenigne cloud API (model={model}, "
            f"{len(payload_frames)} frames, {payload_bytes / 1_000_000:.1f} MB)..."
        )

        def _report(status: str, job: dict) -> None:
            if status == "queued":
                print("[analyze] Queued; waiting for a runner...")
            elif status == "running":
                print("[analyze] Analysis running...")

        return client.analyze(
            target=session.target,
            duration_seconds=session.duration_seconds,
            prompt_template=prompt_template,
            model=model,
            frames=payload_frames,
            on_progress=_report,
        )

    # Dev-only local path (never used in production desktop builds)
    print("[analyze] WARNING: local provider keys (dev only)")
    return _analyze_local(
        session=session,
        session_dir=session_dir,
        frames=frames,
        model=model,
        prompt_template=prompt_template,
        cfg=cfg,
        api_key=api_key,
    )


def _analyze_local(
    session: Session,
    session_dir: Path,
    frames,
    model: str,
    prompt_template: str,
    cfg: Config,
    api_key: Optional[str],
) -> tuple[str, dict]:
    system_prompt = PROMPTS[prompt_template]
    user_content: List[dict] = [
        {
            "type": "text",
            "text": (
                f"Target product: {session.target}\n"
                f"Session duration: {session.duration_seconds:.0f} seconds\n"
                f"Total screenshots: {len(frames)}\n\n"
                f"Below are the timestamped screenshots and aligned narration."
            ),
        }
    ]

    for f in frames:
        img_path = session_dir / f.path
        if not img_path.exists():
            continue
        caption_parts = [f"--- Frame {f.index} @ {f.timestamp_seconds:.1f}s ---"]
        if f.narration:
            caption_parts.append(f"Narration: {f.narration}")
        if f.ocr_text:
            caption_parts.append(f"OCR: {f.ocr_text[:200]}")
        user_content.append({"type": "text", "text": "\n".join(caption_parts)})
        image_data, media_type = encode_frame_image(img_path)
        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{image_data}",
                    "detail": "high",
                },
            }
        )

    model_l = model.lower()
    if "claude" in model_l:
        key = api_key or cfg.anthropic_api_key
        if not key:
            raise RuntimeError("No ANTHROPIC_API_KEY for local Claude call")
        markdown = _call_claude(system_prompt, user_content, model, key)
    elif "grok" in model_l:
        key = api_key or cfg.xai_api_key
        if not key:
            raise RuntimeError("No XAI_API_KEY for local Grok call")
        markdown = _call_grok(system_prompt, user_content, model, key)
    else:
        key = api_key or cfg.openai_api_key
        if not key:
            raise RuntimeError("No OPENAI_API_KEY for local OpenAI call")
        # Convert to OpenAI-compatible content (already image_url form)
        markdown = _call_openai(system_prompt, user_content, model, key)

    return markdown, _extract_json(markdown)


def _call_claude(system_prompt, user_content, model, api_key):
    import anthropic

    # Convert OpenAI-style image_url blocks to Anthropic format
    anthropic_content = []
    for block in user_content:
        if block.get("type") == "image_url":
            url = block["image_url"]["url"]
            media_type = "image/jpeg"
            b64 = url
            if url.startswith("data:") and "," in url:
                header, b64 = url.split(",", 1)
                media_type = header[len("data:") :].split(";", 1)[0] or media_type
            anthropic_content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64,
                    },
                }
            )
        else:
            anthropic_content.append(block)

    client = anthropic.Anthropic(api_key=api_key)
    print(f"[analyze] Calling Claude ({model})...")
    resp = client.messages.create(
        model=model,
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": anthropic_content}],
    )
    return resp.content[0].text


def _call_openai(system_prompt, user_content, model, api_key):
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    print(f"[analyze] Calling OpenAI ({model})...")
    resp = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return resp.choices[0].message.content


def _call_grok(system_prompt, user_content, model, api_key):
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
    print(f"[analyze] Calling Grok ({model})...")
    resp = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return resp.choices[0].message.content


def _extract_json(markdown: str) -> dict:
    matches = re.findall(r"```json\s*(.*?)```", markdown, re.DOTALL)
    if not matches:
        return {}
    try:
        return json.loads(matches[-1])
    except json.JSONDecodeError:
        return {
            "_parse_error": "Could not parse JSON block",
            "_raw": matches[-1][:500],
        }
