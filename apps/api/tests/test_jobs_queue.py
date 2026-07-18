"""
Queue mechanics: claiming, retry/refund, lease recovery, runner auth.

These exercise app.jobs directly rather than through HTTP, because the
interesting behaviour is concurrency and failure handling.
"""

import time
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionLocal, User
from conftest import make_user
from app.jobs import (
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    AnalysisJob,
    claim_next_job,
    create_job,
    run_one_job,
    select_claim_candidate,
    try_claim,
)


@pytest.fixture
def portal():
    from anyio.from_thread import start_blocking_portal

    with start_blocking_portal() as p:
        yield p


async def _truncate_jobs():
    async with SessionLocal() as s:
        await s.execute(delete(AnalysisJob))
        await s.commit()


@pytest.fixture(autouse=True)
def clean_queue(client, portal):
    """
    Start every test in this module with an empty queue.

    claim_next_job() takes the oldest runnable job across all users, so jobs
    left behind by other test modules would be claimed instead of the one
    under test.
    """
    portal.call(_truncate_jobs)
    yield


def _make_user(email: str) -> str:
    """Returns the new user's id. Backend-aware — see conftest.make_user."""
    _, _, user_id = make_user(email)
    return user_id


async def _enqueue(user_id: str, charged: float = 1.0, frames: int = 1) -> str:
    async with SessionLocal() as s:
        user = (await s.execute(select(User).where(User.id == user_id))).scalar_one()
        job = await create_job(
            s,
            user=user,
            target="App",
            duration_seconds=60,
            prompt_template="teardown",
            model="grok-4",
            frames=[{"index": i, "image_b64": "AAAA"} for i in range(frames)],
            charged_minutes=charged,
        )
        return job.id


async def _get(job_id: str) -> AnalysisJob:
    async with SessionLocal() as s:
        return (
            await s.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
        ).scalar_one()


async def _get_user(user_id: str) -> User:
    async with SessionLocal() as s:
        return (
            await s.execute(select(User).where(User.id == user_id))
        ).scalar_one()


def test_interleaved_claims_are_exclusive(portal, client):
    """
    The real race: two runners read the same candidate before either writes.

    Calling claim_next_job twice in sequence does NOT exercise this — the
    second call's SELECT already filters out the claimed job, so the UPDATE
    predicate never runs. This interleaves the phases explicitly so the
    predicate is what decides the winner.
    """
    user_id = _make_user(f"race-{uuid.uuid4().hex[:8]}@example.com")
    job_id = portal.call(_enqueue, user_id)

    async def _race():
        async with SessionLocal() as s1, SessionLocal() as s2:
            now = time.time()
            # Both runners observe the same job as runnable...
            c1 = await select_claim_candidate(s1, now)
            c2 = await select_claim_candidate(s2, now)
            assert c1 is not None and c2 is not None
            assert c1.id == c2.id == job_id
            # ...then both try to take it.
            return (
                await try_claim(s1, c1.id, now, 900),
                await try_claim(s2, c2.id, now, 900),
            )

    won_first, won_second = portal.call(_race)
    assert [won_first, won_second].count(True) == 1, (
        f"expected exactly one winner, got first={won_first} second={won_second}"
    )

    job = portal.call(_get, job_id)
    assert job.status == STATUS_RUNNING
    assert job.attempts == 1, "the loser must not have incremented attempts"


def test_sequential_claims_do_not_double_serve(portal, client):
    user_id = _make_user(f"claim-{uuid.uuid4().hex[:8]}@example.com")
    job_id = portal.call(_enqueue, user_id)

    async def _claim_twice():
        async with SessionLocal() as s1, SessionLocal() as s2:
            a = await claim_next_job(s1, 900)
            b = await claim_next_job(s2, 900)
            return (a.id if a else None), (b.id if b else None)

    first, second = portal.call(_claim_twice)
    assert job_id in (first, second)
    assert first != second, "the same job was handed to two runners"


def test_claimed_job_is_running_with_a_lease(portal, client):
    user_id = _make_user(f"lease-{uuid.uuid4().hex[:8]}@example.com")
    job_id = portal.call(_enqueue, user_id)

    async def _claim():
        async with SessionLocal() as s:
            return await claim_next_job(s, 900)

    portal.call(_claim)
    job = portal.call(_get, job_id)
    assert job.status == STATUS_RUNNING
    assert job.attempts == 1
    assert job.lease_expires_at > time.time()


def test_expired_lease_is_reclaimed(portal, client):
    """A runner that dies mid-flight must not strand the job forever."""
    user_id = _make_user(f"stale-{uuid.uuid4().hex[:8]}@example.com")
    job_id = portal.call(_enqueue, user_id)

    async def _claim_then_expire():
        async with SessionLocal() as s:
            job = await claim_next_job(s, 900)
            job.lease_expires_at = time.time() - 1  # simulate a dead runner
            await s.commit()
            return job.id

    portal.call(_claim_then_expire)

    async def _reclaim():
        async with SessionLocal() as s:
            return await claim_next_job(s, 900)

    reclaimed = portal.call(_reclaim)
    assert reclaimed is not None and reclaimed.id == job_id
    assert reclaimed.attempts == 2


def test_unexpired_lease_is_not_stolen(portal, client):
    user_id = _make_user(f"hold-{uuid.uuid4().hex[:8]}@example.com")
    portal.call(_enqueue, user_id)

    async def _claim():
        async with SessionLocal() as s:
            return await claim_next_job(s, 900)

    assert portal.call(_claim) is not None
    assert portal.call(_claim) is None, "a live lease was stolen"


def test_empty_queue_returns_none(portal, client):
    async def _drain():
        async with SessionLocal() as s:
            while await claim_next_job(s, 900):
                pass
            return await claim_next_job(s, 900)

    assert portal.call(_drain) is None


def test_failure_retries_then_gives_up_and_refunds(portal, client, monkeypatch):
    """
    A failing job retries up to max_attempts, then goes terminal and refunds
    the quota debited at enqueue — the work never happened.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "job_max_attempts", 2)

    async def _boom(*a, **kw):
        raise RuntimeError("provider exploded")

    import app.llm

    monkeypatch.setattr(app.llm, "analyze_with_fallback", _boom)

    user_id = _make_user(f"fail-{uuid.uuid4().hex[:8]}@example.com")

    async def _charge():
        async with SessionLocal() as s:
            u = (await s.execute(select(User).where(User.id == user_id))).scalar_one()
            u.minutes_used_month = 5.0
            # The endpoint sets this via reset_usage_if_needed before
            # enqueueing. A refund is only valid within the period it was
            # debited, so the job must carry a matching period.
            u.usage_month = datetime.now(timezone.utc).strftime("%Y-%m")
            await s.commit()

    portal.call(_charge)
    job_id = portal.call(_enqueue, user_id, 2.0)

    # Attempt 1 -> retryable, back to queued
    portal.call(run_one_job, settings)
    job = portal.call(_get, job_id)
    assert job.status == STATUS_QUEUED
    assert "provider exploded" in job.error

    # Attempt 2 -> terminal
    portal.call(run_one_job, settings)
    job = portal.call(_get, job_id)
    assert job.status == STATUS_FAILED
    assert job.request_json is None, "payload should be released on terminal failure"

    refreshed = portal.call(_get_user, user_id)
    assert refreshed.minutes_used_month == pytest.approx(3.0), "quota was not refunded"


def test_success_clears_payload_and_keeps_charge(portal, client, monkeypatch):
    settings = get_settings()

    async def _ok(*a, **kw):
        return "# Report", {"k": "v"}, "grok-4"

    import app.llm

    monkeypatch.setattr(app.llm, "analyze_with_fallback", _ok)

    user_id = _make_user(f"ok-{uuid.uuid4().hex[:8]}@example.com")

    async def _charge():
        async with SessionLocal() as s:
            u = (await s.execute(select(User).where(User.id == user_id))).scalar_one()
            u.minutes_used_month = 5.0
            await s.commit()

    portal.call(_charge)
    job_id = portal.call(_enqueue, user_id, 2.0)
    portal.call(run_one_job, settings)

    job = portal.call(_get, job_id)
    assert job.status == STATUS_SUCCEEDED
    assert job.result_markdown == "# Report"
    assert job.request_json is None, "payload should be released after success"

    refreshed = portal.call(_get_user, user_id)
    assert refreshed.minutes_used_month == pytest.approx(5.0), "successful work refunded"


def test_public_dict_never_leaks_the_request_payload(portal, client):
    user_id = _make_user(f"leak-{uuid.uuid4().hex[:8]}@example.com")
    job_id = portal.call(_enqueue, user_id, 1.0, 3)
    job = portal.call(_get, job_id)

    body = job.public_dict()
    assert "request_json" not in body
    assert "frames" not in body
    assert "image_b64" not in str(body)


# ---------- Runner trigger endpoint ----------


def test_runner_endpoint_disabled_without_a_secret(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "job_runner_secret", "")
    assert client.post("/v1/internal/jobs/run").status_code == 404


def test_runner_endpoint_rejects_a_wrong_secret(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "job_runner_secret", "correct-horse")
    resp = client.post(
        "/v1/internal/jobs/run", headers={"X-Job-Runner-Secret": "wrong"}
    )
    assert resp.status_code == 401


def test_runner_endpoint_accepts_the_custom_header(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "job_runner_secret", "correct-horse")
    resp = client.post(
        "/v1/internal/jobs/run", headers={"X-Job-Runner-Secret": "correct-horse"}
    )
    assert resp.status_code == 200
    assert "processed" in resp.json()


def test_runner_endpoint_accepts_bearer_via_get(client, settings, monkeypatch):
    """Vercel Cron issues GET with `Authorization: Bearer $CRON_SECRET`."""
    monkeypatch.setattr(settings, "job_runner_secret", "correct-horse")
    resp = client.get(
        "/v1/internal/jobs/run", headers={"Authorization": "Bearer correct-horse"}
    )
    assert resp.status_code == 200


def test_runner_endpoint_needs_no_user_token(client, settings, monkeypatch):
    """It runs as infrastructure; there is no user in that context."""
    monkeypatch.setattr(settings, "job_runner_secret", "correct-horse")
    resp = client.post(
        "/v1/internal/jobs/run", headers={"X-Job-Runner-Secret": "correct-horse"}
    )
    assert resp.status_code == 200
