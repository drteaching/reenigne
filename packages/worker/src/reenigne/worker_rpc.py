"""JSON-RPC over stdin/stdout for the Electron desktop shell."""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

from .capture.ffmpeg_utils import get_display_resolution
from .capture.recorder import ACTIVE_RECORDER
from .config import Config
from .models.session import Session, save_manifest
from .pipeline import _write_metadata, cmd_analyze, cmd_process, cmd_record, cmd_report


def _ok(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _err(id_, message, code=-32000):
    return {
        "jsonrpc": "2.0",
        "id": id_,
        "error": {"code": code, "message": message},
    }


def _session_dir_for(target: str, cfg: Config, output: str | None) -> Path:
    if output:
        return Path(output)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = "".join(c for c in target if c.isalnum() or c in "-_").lower()
    return cfg.output_root / f"{safe}-{stamp}"


def handle(method: str, params: dict, cfg: Config):
    if method == "ping":
        return {"ok": True, "version": __import__("reenigne").__version__}

    if method == "record_start":
        target = params["target"]
        session_dir = _session_dir_for(target, cfg, params.get("output"))
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "screenshots").mkdir(exist_ok=True)
        session = Session(
            target=target,
            display_resolution=get_display_resolution(),
            frame_interval_seconds=cfg.frame_interval_seconds,
        )
        session.session_dir = session_dir
        save_manifest(session, session_dir)
        _write_metadata(session, session_dir, cfg)
        ACTIVE_RECORDER.start(
            session_dir / "recording.mp4",
            video_fps=cfg.video_fps,
            display=params.get("display"),
        )
        return {
            "session_dir": str(session_dir),
            "session_id": session.session_id,
            "recording": True,
        }

    if method == "record_stop":
        session_dir = Path(params["session_dir"])
        duration = ACTIVE_RECORDER.stop()
        from .models.session import load_manifest

        session = load_manifest(session_dir)
        session.duration_seconds = duration
        save_manifest(session, session_dir)
        _write_metadata(session, session_dir, cfg)
        return {"session_dir": str(session_dir), "duration_seconds": duration}

    if method == "record":
        target = params["target"]
        session_dir = _session_dir_for(target, cfg, params.get("output"))
        session = cmd_record(target, session_dir, cfg, display=params.get("display"))
        return {"session_dir": str(session_dir), "session_id": session.session_id}

    if method == "process":
        session_dir = Path(params["session_dir"])
        if params.get("no_ocr"):
            cfg.enable_ocr = False
        session = cmd_process(session_dir, cfg, force=bool(params.get("force")))
        return {
            "session_dir": str(session_dir),
            "frames": len(session.frames),
            "segments": len(session.transcript_segments),
        }

    if method == "analyze":
        session_dir = Path(params["session_dir"])
        md, features = cmd_analyze(
            session_dir,
            cfg,
            model=params.get("model"),
            prompt=params.get("prompt", "teardown"),
        )
        return {
            "session_dir": str(session_dir),
            "analysis_chars": len(md),
            "features_keys": list(features.keys()) if isinstance(features, dict) else [],
        }

    if method == "report":
        session_dir = Path(params["session_dir"])
        path = cmd_report(session_dir, fmt=params.get("format", "html"))
        return {"path": str(path)}

    if method == "list_sessions":
        root = Path(params.get("output_root") or cfg.output_root).expanduser()
        if not root.exists():
            return {"sessions": []}
        sessions = []
        for d in sorted(root.iterdir(), reverse=True):
            if d.is_dir() and (d / "manifest.json").exists():
                sessions.append({"path": str(d), "name": d.name})
        return {"sessions": sessions}

    raise ValueError(f"Unknown method: {method}")


def main():
    cfg = Config.from_env()
    # Token may be injected by Electron via env REENIGNE_API_TOKEN
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            id_ = req.get("id")
            method = req.get("method")
            params = req.get("params") or {}
            # Refresh token each call
            cfg = Config.from_env()
            result = handle(method, params, cfg)
            print(json.dumps(_ok(id_, result)), flush=True)
        except Exception as e:
            tb = traceback.format_exc()
            print(
                json.dumps(_err(req.get("id") if "req" in dir() else None, f"{e}\n{tb}")),
                flush=True,
            )


if __name__ == "__main__":
    main()
