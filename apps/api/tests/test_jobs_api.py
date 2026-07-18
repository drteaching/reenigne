"""The async analysis job endpoints."""

import pytest

from app import main as main_module
from app.config import get_settings


@pytest.fixture
def fake_provider(monkeypatch):
    """Replace the provider call; returns a dict recording what it saw."""
    seen = {"calls": 0, "frames": None}

    async def _fake(settings, **kw):
        seen["calls"] += 1
        seen["frames"] = len(kw["frames"])
        seen["target"] = kw["target"]
        return "# Teardown\n\nFindings.", {"features": ["a"]}, "grok-4"

    monkeypatch.setattr("app.jobs.analyze_with_fallback", _fake, raising=False)
    monkeypatch.setattr(main_module, "analyze_with_fallback", _fake)
    import app.llm

    monkeypatch.setattr(app.llm, "analyze_with_fallback", _fake)
    return seen


@pytest.fixture
def inline_runner(monkeypatch):
    """Execute jobs synchronously at enqueue, as a persistent host would."""
    monkeypatch.setattr(get_settings(), "job_run_inline", True)


def _submit(client, headers, frames=1, **kw):
    body = {
        "target": kw.get("target", "Acme App"),
        "duration_seconds": kw.get("duration_seconds", 120),
        "frames": [
            {"index": i, "image_b64": "AAAA", "timestamp_seconds": float(i)}
            for i in range(frames)
        ],
    }
    return client.post("/v1/analyze/jobs", headers=headers, json=body)


def test_submit_returns_202_with_job_id(client, subscribed_user, fake_provider):
    _, headers = subscribed_user
    resp = _submit(client, headers)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"]
    assert body["status"] == "queued"
    assert body["poll_url"] == f"/v1/analyze/jobs/{body['job_id']}"


def test_submit_does_not_call_the_provider(client, subscribed_user, fake_provider):
    """The whole point: enqueueing must not block on the LLM."""
    _, headers = subscribed_user
    _submit(client, headers)
    assert fake_provider["calls"] == 0


def test_job_completes_and_returns_result(
    client, subscribed_user, fake_provider, inline_runner
):
    _, headers = subscribed_user
    job_id = _submit(client, headers).json()["job_id"]

    resp = client.get(f"/v1/analyze/jobs/{job_id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["markdown"].startswith("# Teardown")
    assert body["features"] == {"features": ["a"]}
    assert body["model_used"] == "grok-4"
    assert fake_provider["calls"] == 1


def test_pending_job_reports_queued_without_result(
    client, subscribed_user, fake_provider
):
    _, headers = subscribed_user
    job_id = _submit(client, headers).json()["job_id"]

    body = client.get(f"/v1/analyze/jobs/{job_id}", headers=headers).json()
    assert body["status"] == "queued"
    assert "markdown" not in body


def test_job_is_not_readable_by_another_user(
    client, subscribed_user, other_user, fake_provider
):
    _, owner_headers = subscribed_user
    job_id = _submit(client, owner_headers).json()["job_id"]

    _, other_headers = other_user
    resp = client.get(f"/v1/analyze/jobs/{job_id}", headers=other_headers)
    assert resp.status_code == 404, "must not confirm another user's job exists"


def test_job_requires_authentication(client, subscribed_user, fake_provider):
    _, headers = subscribed_user
    job_id = _submit(client, headers).json()["job_id"]
    assert client.get(f"/v1/analyze/jobs/{job_id}").status_code == 401


def test_submit_requires_subscription(client, user, fake_provider):
    _, headers = user
    assert _submit(client, headers).status_code == 402


def test_submit_rejects_empty_frames(client, subscribed_user, fake_provider):
    _, headers = subscribed_user
    resp = client.post(
        "/v1/analyze/jobs",
        headers=headers,
        json={"target": "App", "frames": [], "duration_seconds": 10},
    )
    assert resp.status_code == 400


def test_frames_downsampled_to_entitlement(
    client, subscribed_user, fake_provider, inline_runner
):
    """pro_max_frames_per_session is 5 in the test config."""
    _, headers = subscribed_user
    _submit(client, headers, frames=25)
    assert fake_provider["frames"] == 5


def test_active_job_cap_enforced(client, subscribed_user, fake_provider, settings):
    """Queued jobs accumulate; the 4th must be rejected (cap is 3)."""
    _, headers = subscribed_user
    for _ in range(settings.job_max_active_per_user):
        assert _submit(client, headers).status_code == 202
    resp = _submit(client, headers)
    assert resp.status_code == 429
    assert "in progress" in resp.json()["detail"]


def test_listing_returns_only_own_jobs(client, subscribed_user, other_user, fake_provider):
    _, owner_headers = subscribed_user
    _submit(client, owner_headers)

    _, other_headers = other_user
    body = client.get("/v1/analyze/jobs", headers=other_headers).json()
    assert body["jobs"] == []
