"""Provider adapters: Grok primary, OpenAI / Anthropic fallbacks."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from .config import Settings
from .prompts import PROMPTS

# Providers are called from async request handlers, so every client here must
# be the async variant — a sync client blocks the whole event loop for the
# duration of a multi-minute vision call.
DEFAULT_MEDIA_TYPE = "image/jpeg"


def extract_json(markdown: str) -> dict:
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


def _build_openai_style_content(frames: list[dict[str, Any]], meta: dict) -> list[dict]:
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Target product: {meta['target']}\n"
                f"Session duration: {meta['duration_seconds']:.0f} seconds\n"
                f"Total screenshots: {len(frames)}\n\n"
                "Below are the timestamped screenshots and aligned narration."
            ),
        }
    ]
    for f in frames:
        caption = [f"--- Frame {f['index']} @ {f.get('timestamp_seconds', 0):.1f}s ---"]
        if f.get("narration"):
            caption.append(f"Narration: {f['narration']}")
        if f.get("ocr_text"):
            caption.append(f"OCR: {f['ocr_text'][:200]}")
        content.append({"type": "text", "text": "\n".join(caption)})
        b64 = f.get("image_b64", "")
        if b64:
            media_type = f.get("media_type") or DEFAULT_MEDIA_TYPE
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{b64}",
                        "detail": "high",
                    },
                }
            )
    return content


def _to_anthropic_content(user_content: list[dict]) -> list[dict]:
    out = []
    for block in user_content:
        if block.get("type") == "image_url":
            url = block["image_url"]["url"]
            media_type = DEFAULT_MEDIA_TYPE
            b64 = url
            if url.startswith("data:") and "," in url:
                header, b64 = url.split(",", 1)
                media_type = header[len("data:") :].split(";", 1)[0] or media_type
            out.append(
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
            out.append(block)
    return out


async def call_grok(
    settings: Settings, system: str, content: list[dict], model: str
) -> str:
    if not settings.xai_api_key:
        raise RuntimeError("XAI_API_KEY not configured on server")
    client = AsyncOpenAI(api_key=settings.xai_api_key, base_url="https://api.x.ai/v1")
    resp = await client.chat.completions.create(
        model=model,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    )
    return resp.choices[0].message.content or ""


async def call_openai(
    settings: Settings, system: str, content: list[dict], model: str
) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured on server")
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=model,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    )
    return resp.choices[0].message.content or ""


async def call_claude(
    settings: Settings, system: str, content: list[dict], model: str
) -> str:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured on server")
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=model,
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": _to_anthropic_content(content)}],
    )
    return resp.content[0].text


def resolve_model_chain(requested: str, settings: Settings) -> list[tuple[str, str]]:
    """
    Return ordered list of (provider, model_id).
    provider in: grok | openai | anthropic
    """
    requested = (requested or settings.default_model).strip()
    chain: list[tuple[str, str]] = []

    def classify(m: str) -> tuple[str, str]:
        ml = m.lower()
        if "claude" in ml:
            return "anthropic", m
        if "grok" in ml:
            return "grok", m
        return "openai", m

    chain.append(classify(requested))
    for fb in settings.fallback_models.split(","):
        fb = fb.strip()
        if not fb:
            continue
        item = classify(fb)
        if item not in chain:
            chain.append(item)
    return chain


async def analyze_with_fallback(
    settings: Settings,
    *,
    prompt_template: str,
    model: str,
    target: str,
    duration_seconds: float,
    frames: list[dict[str, Any]],
) -> tuple[str, dict, str]:
    """Returns (markdown, features, model_used)."""
    if prompt_template not in PROMPTS:
        raise ValueError(f"Unknown prompt template: {prompt_template}")

    system = PROMPTS[prompt_template]
    content = _build_openai_style_content(
        frames,
        {"target": target, "duration_seconds": duration_seconds},
    )

    errors: list[str] = []
    for provider, mid in resolve_model_chain(model, settings):
        try:
            if provider == "grok":
                md = await call_grok(settings, system, content, mid)
            elif provider == "anthropic":
                md = await call_claude(settings, system, content, mid)
            else:
                md = await call_openai(settings, system, content, mid)
            return md, extract_json(md), mid
        except Exception as e:
            errors.append(f"{provider}/{mid}: {e}")
            continue

    raise RuntimeError("All LLM providers failed: " + " | ".join(errors))


async def transcribe_whisper(
    settings: Settings, audio_bytes: bytes, filename: str
) -> list[dict]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured on server")
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    import io

    bio = io.BytesIO(audio_bytes)
    bio.name = filename
    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=bio,
        response_format="verbose_json",
        timestamp_granularities=["segment"],
    )
    segments = []
    for seg in response.segments or []:
        segments.append(
            {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
            }
        )
    return segments
