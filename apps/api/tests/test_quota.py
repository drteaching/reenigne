"""
Quota must be checked BEFORE billable provider calls.

The original code charged Whisper/the LLM first and only then compared usage
to the limit, so an over-quota account could keep spending indefinitely.
"""

import pytest

from app import main as main_module
from app.db import SessionLocal, User
from sqlalchemy import select


async def _set_usage(email: str, minutes: float):
    async with SessionLocal() as s:
        user = (
            await s.execute(select(User).where(User.email == email))
        ).scalar_one()
        user.minutes_used_month = minutes
        await s.commit()


@pytest.fixture
def exhaust_quota(client, subscribed_user):
    """Put the user at their monthly limit (10 minutes in the test config)."""
    from anyio.from_thread import start_blocking_portal

    email, headers = subscribed_user
    with start_blocking_portal() as portal:
        portal.call(_set_usage, email, 10.0)
    return email, headers


def test_analyze_rejected_when_quota_exhausted(client, exhaust_quota, monkeypatch):
    _, headers = exhaust_quota

    called = False

    async def _should_not_run(*a, **kw):
        nonlocal called
        called = True
        return "md", {}, "grok-4"

    monkeypatch.setattr(main_module, "analyze_with_fallback", _should_not_run)

    resp = client.post(
        "/v1/analyze",
        headers=headers,
        json={"target": "App", "frames": [], "duration_seconds": 60},
    )
    assert resp.status_code == 402
    assert not called, "provider was called despite the quota being exhausted"


def test_transcribe_rejected_when_quota_exhausted(client, exhaust_quota, monkeypatch):
    _, headers = exhaust_quota

    called = False

    async def _should_not_run(*a, **kw):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(main_module, "transcribe_whisper", _should_not_run)

    resp = client.post(
        "/v1/transcribe",
        headers=headers,
        files={"file": ("a.wav", b"fake-audio", "audio/wav")},
    )
    assert resp.status_code == 402
    assert not called, "Whisper was called despite the quota being exhausted"


def test_analyze_succeeds_within_quota(client, subscribed_user, monkeypatch):
    _, headers = subscribed_user

    async def _fake(*a, **kw):
        return "# Teardown", {"features": []}, "grok-4"

    monkeypatch.setattr(main_module, "analyze_with_fallback", _fake)

    resp = client.post(
        "/v1/analyze",
        headers=headers,
        json={"target": "App", "frames": [], "duration_seconds": 60},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["model_used"] == "grok-4"


def test_oversized_upload_rejected(client, subscribed_user, monkeypatch):
    """413 before buffering the whole body, and before calling Whisper."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_audio_upload_bytes", 1024, raising=False)

    called = False

    async def _should_not_run(*a, **kw):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(main_module, "transcribe_whisper", _should_not_run)

    _, headers = subscribed_user
    resp = client.post(
        "/v1/transcribe",
        headers=headers,
        files={"file": ("big.wav", b"x" * (4 * 1024 * 1024), "audio/wav")},
    )
    assert resp.status_code == 413
    assert not called


def test_frames_downsampled_to_entitlement(client, subscribed_user, monkeypatch):
    """Server caps frames at pro_max_frames_per_session (5 in test config)."""
    seen = {}

    async def _capture(settings, **kw):
        seen["count"] = len(kw["frames"])
        return "md", {}, "grok-4"

    monkeypatch.setattr(main_module, "analyze_with_fallback", _capture)

    _, headers = subscribed_user
    frames = [
        {"index": i, "image_b64": "AAAA", "timestamp_seconds": float(i)}
        for i in range(20)
    ]
    resp = client.post(
        "/v1/analyze",
        headers=headers,
        json={"target": "App", "frames": frames, "duration_seconds": 60},
    )
    assert resp.status_code == 200, resp.text
    assert seen["count"] == 5
