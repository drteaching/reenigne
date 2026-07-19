"""Provider adapters: Grok primary, OpenAI / Anthropic fallbacks."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from reenigne_prompts import PROMPTS

from .config import Settings

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


def first_text_block(blocks: Any) -> str:
    """
    The first text block of an Anthropic response.

    Indexing content[0].text assumes the first block is text, which is only
    reliably true today. A response may lead with a thinking block, a
    tool_use block, or any future block type, and content[0].text would then
    raise AttributeError mid-analysis — losing a completed, already-paid-for
    vision call to a crash in the last line of the adapter.
    """
    for block in blocks or []:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", None)
            if text is not None:
                return text

    kinds = [getattr(b, "type", "?") for b in (blocks or [])]
    raise RuntimeError(
        f"Anthropic response contained no text block (types: {kinds or 'none'})"
    )


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
    return first_text_block(resp.content)


class UnknownModel(ValueError):
    """A requested model is not in the allowlist."""


def model_registry(settings: Settings) -> dict[str, str]:
    """
    The single model id -> provider map.

    Replaces substring guessing ("claude" in the name means Anthropic), which
    silently mis-routed anything unrecognised to OpenAI: a typo like "gpt4o"
    became a live OpenAI call that failed at the provider with an opaque
    error, and a hypothetical "grok-claude-mix" would have gone to Anthropic
    on a coincidence.

    Built from settings so the ids are configurable in one place, and shared
    with the triage path (see provider_for) so a misconfigured TRIAGE_MODEL
    cannot be sent to the wrong provider either.
    """
    return {
        settings.grok_model: "grok",
        settings.openai_model: "openai",
        settings.anthropic_model: "anthropic",
        settings.openai_mini_model: "openai",
    }


def provider_for(model: str, settings: Settings) -> str:
    """Provider for one model id. Raises UnknownModel if not allowlisted."""
    registry = model_registry(settings)
    provider = registry.get((model or "").strip())
    if provider is None:
        raise UnknownModel(
            f"Unknown model {model!r}. Available: "
            f"{', '.join(sorted(registry))}."
        )
    return provider


def resolve_model_chain(requested: str, settings: Settings) -> list[tuple[str, str]]:
    """
    Ordered [(provider, model_id)] — the requested model, then fallbacks.

    Raises UnknownModel for anything outside the allowlist so a bad value is
    rejected at submit time rather than guessed at.
    """
    requested = (requested or settings.default_model).strip()
    chain: list[tuple[str, str]] = [(provider_for(requested, settings), requested)]

    for fb in settings.fallback_models.split(","):
        fb = fb.strip()
        if not fb:
            continue
        # A misconfigured fallback must not take down a valid request, so an
        # unknown one is skipped rather than raised on. The requested model is
        # the user's input and is validated strictly; fallbacks are ours.
        try:
            item = (provider_for(fb, settings), fb)
        except UnknownModel:
            continue
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


# Transcription models that support `verbose_json` and therefore
# `timestamp_granularities=["segment"]`.
#
# As of openai-python 2.46 the SDK's generated docs state that for
# `gpt-4o-transcribe` and `gpt-4o-mini-transcribe` "the only supported format
# is `json`", and `gpt-4o-transcribe-diarize` supports only `json`, `text` and
# `diarized_json`. None of them can return segment timestamps, so none can
# replace whisper-1 here without breaking frame alignment.
#
# Revisit when OpenAI ships a newer model that supports verbose_json; add it
# here and the setting can move.
TRANSCRIPTION_MODELS_WITH_SEGMENTS = frozenset({"whisper-1"})


async def transcribe_whisper(
    settings: Settings, audio_bytes: bytes, filename: str
) -> list[dict]:
    """
    Transcribe audio into timestamped segments.

    The segment contract is load-bearing: align_transcript_to_frames matches
    each segment's start time to the frame that was on screen, and that
    alignment is what lets a report cite the frame behind an observation. A
    model that returns only a flat string would leave every narration line
    attached to nothing.
    """
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured on server")

    model = settings.transcription_model
    if model not in TRANSCRIPTION_MODELS_WITH_SEGMENTS:
        # Fail loudly at the call rather than returning segment-less output
        # that would quietly misalign every narration line.
        raise RuntimeError(
            f"TRANSCRIPTION_MODEL={model!r} does not return segment "
            f"timestamps. Frame alignment depends on them. Supported: "
            f"{', '.join(sorted(TRANSCRIPTION_MODELS_WITH_SEGMENTS))}."
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    import io

    bio = io.BytesIO(audio_bytes)
    bio.name = filename
    response = await client.audio.transcriptions.create(
        model=model,
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


async def call_text_model(
    settings: Settings, *, system: str, user: str, model: str
) -> str:
    """
    One text-only completion. Used by feedback triage.

    Separate from analyze_with_fallback: that path builds multimodal content
    and walks a provider chain sized for expensive vision work. Triage is a
    cheap single call, and a fallback cascade on it would multiply the cost of
    something that runs on every submission.
    """
    # Routed through the same registry as analysis. Previously this assumed
    # OpenAI, so setting TRIAGE_MODEL to a Claude id would have sent an
    # Anthropic model name to OpenAI and failed confusingly.
    provider = provider_for(model, settings)
    if provider != "openai":
        raise RuntimeError(
            f"TRIAGE_MODEL={model!r} routes to {provider}, but triage only "
            f"supports OpenAI-compatible chat completions today."
        )
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured on server")
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=model,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""
