"""
The runner must not start work it cannot finish.

On Vercel the runner executes inside an invocation with a hard maxDuration.
A provider call that overruns is killed mid-flight: the job's lease survives,
so it is retried later, and the tokens already spent on the killed attempt are
billed for nothing. Draining several jobs sequentially in one invocation makes
that near-certain.

So the runner tracks remaining invocation budget and declines to claim a job
without enough runway to plausibly finish it.
"""

import time
import uuid

import pytest
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionLocal, User
from app.jobs import STATUS_QUEUED, AnalysisJob, create_job, run_pending_jobs
from conftest import make_user


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
    portal.call(_truncate_jobs)
    yield


async def _enqueue(user_id: str) -> str:
    async with SessionLocal() as s:
        user = (await s.execute(select(User).where(User.id == user_id))).scalar_one()
        job = await create_job(
            s,
            user=user,
            target="App",
            duration_seconds=60,
            prompt_template="teardown",
            model="grok-4",
            frames=[{"index": 0, "image_b64": "AAAA"}],
            charged_minutes=1.0,
        )
        return job.id


async def _status(job_id: str) -> str:
    async with SessionLocal() as s:
        job = (
            await s.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
        ).scalar_one()
        return job.status


@pytest.fixture
def provider(monkeypatch):
    calls = {"n": 0}

    async def _fake(settings, **kw):
        calls["n"] += 1
        return "# ok", {}, "grok-4"

    import app.llm

    monkeypatch.setattr(app.llm, "analyze_with_fallback", _fake)
    return calls


def test_declines_to_claim_without_enough_runway(portal, provider, monkeypatch):
    """An exhausted budget must leave the job queued and spend nothing."""
    settings = get_settings()
    monkeypatch.setattr(settings, "job_min_runway_seconds", 120)

    _, _, user_id = make_user(f"runway-{uuid.uuid4().hex[:6]}@example.com")
    job_id = portal.call(_enqueue, user_id)

    # Deadline already in the past: zero runway.
    result = portal.call(
        lambda: run_pending_jobs(settings, deadline=time.monotonic() - 1)
    )

    assert result["processed"] == 0
    assert result["stopped"] == "insufficient_runway"
    assert provider["n"] == 0, "provider was called with no runway"
    assert portal.call(_status, job_id) == STATUS_QUEUED, "job should stay claimable"


def test_declines_when_runway_is_below_the_threshold(portal, provider, monkeypatch):
    """Some budget left, but not enough to plausibly finish a job."""
    settings = get_settings()
    monkeypatch.setattr(settings, "job_min_runway_seconds", 300)

    _, _, user_id = make_user(f"short-{uuid.uuid4().hex[:6]}@example.com")
    job_id = portal.call(_enqueue, user_id)

    result = portal.call(
        lambda: run_pending_jobs(settings, deadline=time.monotonic() + 30)
    )

    assert result["processed"] == 0
    assert result["stopped"] == "insufficient_runway"
    assert provider["n"] == 0
    assert portal.call(_status, job_id) == STATUS_QUEUED


def test_runs_when_runway_is_sufficient(portal, provider, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "job_min_runway_seconds", 10)

    _, _, user_id = make_user(f"ample-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(_enqueue, user_id)

    result = portal.call(
        lambda: run_pending_jobs(settings, deadline=time.monotonic() + 600)
    )

    assert result["processed"] == 1
    assert provider["n"] == 1


def test_default_batch_size_is_one(portal, provider, monkeypatch):
    """
    One job per invocation by default.

    Draining several sequentially in a single capped invocation is what makes
    an overrun near-certain.
    """
    settings = get_settings()
    assert settings.job_runner_batch_size == 1

    monkeypatch.setattr(settings, "job_min_runway_seconds", 10)
    _, _, user_id = make_user(f"batch-{uuid.uuid4().hex[:6]}@example.com")
    for _ in range(3):
        portal.call(_enqueue, user_id)

    result = portal.call(
        lambda: run_pending_jobs(settings, deadline=time.monotonic() + 600)
    )
    assert result["processed"] == 1
    assert result["stopped"] == "batch_limit"
    assert provider["n"] == 1


def test_stops_when_the_queue_empties(portal, provider, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "job_min_runway_seconds", 10)

    result = portal.call(
        lambda: run_pending_jobs(settings, limit=5, deadline=time.monotonic() + 600)
    )
    assert result["processed"] == 0
    assert result["stopped"] == "queue_empty"


def test_stops_at_deadline_partway_through_a_batch(portal, monkeypatch):
    """
    A batch larger than one stops once the budget runs down.

    Uses a controlled clock rather than wall time: the stubbed provider
    returns instantly, so real elapsed time would never approach the
    threshold and the test would assert nothing.
    """
    import types

    import app.jobs as jobs_module
    import app.llm

    settings = get_settings()
    monkeypatch.setattr(settings, "job_min_runway_seconds", 300)

    clock = {"t": 1000.0}
    fake_time = types.SimpleNamespace(monotonic=lambda: clock["t"], time=time.time)
    monkeypatch.setattr(jobs_module, "time", fake_time)

    calls = {"n": 0}

    async def _burns_200s(settings, **kw):
        calls["n"] += 1
        clock["t"] += 200  # each job consumes 200s of the budget
        return "# ok", {}, "grok-4"

    monkeypatch.setattr(app.llm, "analyze_with_fallback", _burns_200s)

    _, _, user_id = make_user(f"partial-{uuid.uuid4().hex[:6]}@example.com")
    for _ in range(4):
        portal.call(_enqueue, user_id)

    # Budget 500s, threshold 300s, 200s per job:
    #   500 >= 300 -> run (t=1200) | 300 >= 300 -> run (t=1400) | 100 < 300 -> stop
    result = portal.call(lambda: run_pending_jobs(settings, limit=4, deadline=1500.0))

    assert result["processed"] == 2
    assert result["stopped"] == "insufficient_runway"
    assert calls["n"] == 2


def test_result_reports_remaining_runway(portal, provider, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "job_min_runway_seconds", 10)
    result = portal.call(
        lambda: run_pending_jobs(settings, deadline=time.monotonic() + 123)
    )
    assert 0 < result["runway_seconds"] <= 123
