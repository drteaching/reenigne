"""End-to-end orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .analyze.llm_client import analyze_session
from .capture.ffmpeg_utils import get_display_resolution
from .capture.screen import record_screen_and_audio
from .cloud import CloudAPIError, CloudClient
from .config import Config
from .models.session import Session, load_manifest, save_manifest
from .process.align import align_transcript_to_frames
from .process.frames import extract_frames
from .process.ocr import ocr_available, ocr_frame
from .process.transcribe import extract_audio, transcribe_audio
from .render.html import render_html_report


def cmd_record(
    target: str,
    session_dir: Path,
    cfg: Config,
    display: Optional[int] = None,
) -> Session:
    """Start a new recording session."""
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "screenshots").mkdir(exist_ok=True)

    session = Session(
        target=target,
        display_resolution=get_display_resolution(),
        frame_interval_seconds=cfg.frame_interval_seconds,
    )
    session.session_dir = session_dir

    video_path = session_dir / "recording.mp4"
    duration = record_screen_and_audio(
        video_path,
        video_fps=cfg.video_fps,
        display=display,
    )
    session.duration_seconds = duration

    # PRD metadata.json alongside manifest
    _write_metadata(session, session_dir, cfg)

    save_manifest(session, session_dir)
    print(f"[pipeline] Session saved to {session_dir}")
    return session


def cmd_process(
    session_dir: Path,
    cfg: Config,
    force: bool = False,
) -> Session:
    """Extract frames, transcribe audio, align."""
    session = load_manifest(session_dir)
    video_path = session_dir / "recording.mp4"
    if not video_path.exists():
        raise FileNotFoundError(f"No recording.mp4 in {session_dir}")

    if session.frames and not force:
        print("[pipeline] Frames already present; use --force to re-process.")
    else:
        frames = extract_frames(
            video_path=video_path,
            output_dir=session_dir / "screenshots",
            interval_seconds=session.frame_interval_seconds,
            dedupe=True,
            phash_threshold=cfg.phash_similarity_threshold,
        )
        session.frames = frames

    audio_wav = session_dir / "audio.wav"
    extract_audio(video_path, audio_wav)

    try:
        if cfg.api_token:
            client = CloudClient(cfg.api_base_url, cfg.api_token)
            print("[pipeline] Transcribing via reenigne cloud API...")
            segments = client.transcribe(audio_wav)
        elif cfg.openai_api_key:
            print("[pipeline] WARNING: using local OPENAI_API_KEY (dev only)")
            segments = transcribe_audio(
                audio_wav,
                api_key=cfg.openai_api_key,
                model=cfg.whisper_model,
            )
        else:
            raise CloudAPIError(
                "No REENIGNE_API_TOKEN. Sign in via the desktop app or set "
                "REENIGNE_API_TOKEN for CLI access.",
                401,
            )
        session.transcript_segments = segments
        session.frames = align_transcript_to_frames(session.frames, segments)
    except CloudAPIError as e:
        print(f"[pipeline] Transcription skipped/failed: {e}")
        if e.status_code == 402:
            raise

    if cfg.enable_ocr and ocr_available():
        print("[pipeline] Running OCR on frames...")
        for f in session.frames:
            f.ocr_text = ocr_frame(session_dir / f.path)

    save_manifest(session, session_dir)
    (session_dir / "transcript.md").write_text(
        _transcript_to_markdown(session), encoding="utf-8"
    )
    _write_metadata(session, session_dir, cfg)

    print("[pipeline] Processing complete. Manifest updated.")
    return session


def cmd_analyze(
    session_dir: Path,
    cfg: Config,
    model: Optional[str] = None,
    prompt: str = "teardown",
) -> tuple[str, dict]:
    """Send session to LLM and produce analysis outputs."""
    session = load_manifest(session_dir)
    model = model or cfg.default_llm_model

    markdown, structured = analyze_session(
        session=session,
        session_dir=session_dir,
        model=model,
        prompt_template=prompt,
        cfg=cfg,
    )

    (session_dir / "analysis.md").write_text(markdown, encoding="utf-8")
    (session_dir / "features.json").write_text(
        json.dumps(structured, indent=2), encoding="utf-8"
    )

    print("[pipeline] Analysis saved.")
    return markdown, structured


def cmd_report(session_dir: Path, fmt: str = "html") -> Path:
    """Render report in html, md, or json form."""
    session = load_manifest(session_dir)
    analysis_path = session_dir / "analysis.md"
    analysis = (
        analysis_path.read_text(encoding="utf-8")
        if analysis_path.exists()
        else "*(no analysis run yet)*"
    )

    if fmt == "md":
        out = session_dir / "analysis.md"
        print(f"[pipeline] Markdown report: {out}")
        return out
    if fmt == "json":
        features = session_dir / "features.json"
        if not features.exists():
            features.write_text("{}", encoding="utf-8")
        print(f"[pipeline] JSON report: {features}")
        return features

    path = render_html_report(session, session_dir, analysis)
    print(f"[pipeline] HTML report: {path}")
    return path


def _transcript_to_markdown(session: Session) -> str:
    lines = [f"# Transcript — {session.target}\n"]
    for seg in session.transcript_segments:
        lines.append(f"**[{seg.start:.1f}s]** {seg.text}\n")
    return "\n".join(lines)


def _write_metadata(session: Session, session_dir: Path, cfg: Config) -> None:
    meta = {
        "session_id": session.session_id,
        "target_name": session.target,
        "started_at": session.started_at,
        "duration_seconds": session.duration_seconds,
        "display_resolution": session.display_resolution,
        "config": {
            "frame_interval_seconds": session.frame_interval_seconds,
            "default_llm_model": cfg.default_llm_model,
            "enable_ocr": cfg.enable_ocr,
        },
    }
    (session_dir / "metadata.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
