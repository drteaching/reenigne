"""
Per-report metering: an analyses-per-month allowance alongside minutes.

The credit is charged on success only, so there is no reservation to refund.
That alone would not enforce the limit — at 29/30 a user could enqueue three
jobs, each passing `29 < 30`, and finish at 32 — so the enqueue check counts
in-flight jobs toward the allowance.
"""

import uuid
from datetime import datetime, timezone
from functools import partial

import pytest
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionLocal, User
from app.jobs import (
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    AnalysisJob,
    create_job,
    run_one_job,
)
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


def _this_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _set_usage(user_id, minutes=0.0, analyses=0, month=None):
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == user_id))).scalar_one()
        u.minutes_used_month = minutes
        u.analyses_used_month = analyses
        u.usage_month = month if month is not None else _this_month()
        await s.commit()


async def _get_user(user_id) -> User:
    async with SessionLocal() as s:
        return (
            await s.execute(select(User).where(User.id == user_id))
        ).scalar_one()


async def _count_jobs(user_id) -> int:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(AnalysisJob).where(AnalysisJob.user_id == user_id)
            )
        ).scalars().all()
        return len(rows)


async def _enqueue_direct(user_id, charged=1.0, month=None) -> str:
    """Insert a job bypassing the endpoint, to set up in-flight state."""
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
            charged_minutes=charged,
        )
        if month is not None:
            job.usage_month = month
            await s.commit()
        return job.id


async def _get_job(job_id) -> AnalysisJob:
    async with SessionLocal() as s:
        return (
            await s.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
        ).scalar_one()


def _submit(client, headers):
    return client.post(
        "/v1/analyze/jobs",
        headers=headers,
        json={
            "target": "App",
            "duration_seconds": 60,
            "frames": [{"index": 0, "image_b64": "AAAA"}],
        },
    )


@pytest.fixture
def ok_provider(monkeypatch):
    calls = {"n": 0}

    async def _fake(settings, **kw):
        calls["n"] += 1
        return "# Report", {"k": "v"}, "grok-4"

    import app.llm

    monkeypatch.setattr(app.llm, "analyze_with_fallback", _fake)
    return calls


# ---------- Allowance enforcement at enqueue ----------


def test_analysis_beyond_the_allowance_is_rejected(client, portal, ok_provider):
    """N+1 in a month: 402 naming the analyses limit, no job row, no debit."""
    settings = get_settings()
    _, headers, user_id = make_user(f"cap-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_usage, user_id, analyses=settings.pro_analyses_per_month, minutes=0.0
    ))

    resp = _submit(client, headers)

    assert resp.status_code == 402, resp.text
    detail = resp.json()["detail"].lower()
    assert "analys" in detail, f"402 must name the analyses limit: {detail}"
    assert str(settings.pro_analyses_per_month) in resp.json()["detail"]

    assert portal.call(_count_jobs, user_id) == 0, "rejected submit created a job"
    user = portal.call(_get_user, user_id)
    assert user.minutes_used_month == 0.0, "rejected submit debited minutes"
    assert user.analyses_used_month == settings.pro_analyses_per_month


def test_minutes_limit_names_minutes(client, portal, ok_provider):
    settings = get_settings()
    _, headers, user_id = make_user(f"min-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_usage, user_id, minutes=float(settings.pro_minutes_per_month), analyses=0
    ))

    resp = _submit(client, headers)
    assert resp.status_code == 402
    assert "minute" in resp.json()["detail"].lower()


def test_in_flight_jobs_count_toward_the_allowance(client, portal, ok_provider):
    """
    Charging on success only would let several concurrent jobs each pass the
    check and collectively overshoot. Queued work must occupy the allowance.
    """
    settings = get_settings()
    _, headers, user_id = make_user(f"flight-{uuid.uuid4().hex[:6]}@example.com")

    # One credit left, and one job already in flight consuming it.
    portal.call(partial(_set_usage, user_id, analyses=settings.pro_analyses_per_month - 1, minutes=0.0
    ))
    portal.call(_enqueue_direct, user_id)

    resp = _submit(client, headers)
    assert resp.status_code == 402
    assert "analys" in resp.json()["detail"].lower()


def test_submit_allowed_with_allowance_remaining(client, portal, ok_provider):
    settings = get_settings()
    _, headers, user_id = make_user(f"okay-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_usage, user_id, analyses=settings.pro_analyses_per_month - 1, minutes=0.0
    ))

    assert _submit(client, headers).status_code == 202


# ---------- Charging on success ----------


def test_success_charges_exactly_one_analysis(portal, ok_provider):
    settings = get_settings()
    _, _, user_id = make_user(f"charge-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_usage, user_id, analyses=4, minutes=1.0))
    job_id = portal.call(_enqueue_direct, user_id)

    portal.call(run_one_job, settings)

    assert portal.call(_get_job, job_id).status == STATUS_SUCCEEDED
    user = portal.call(_get_user, user_id)
    assert user.analyses_used_month == 5


def test_enqueue_does_not_charge_an_analysis(client, portal, ok_provider):
    """The credit is spent on success, not on submission."""
    _, headers, user_id = make_user(f"noearly-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_usage, user_id, analyses=0, minutes=0.0))

    assert _submit(client, headers).status_code == 202
    assert portal.call(_get_user, user_id).analyses_used_month == 0


def test_retries_never_charge_an_analysis(portal, monkeypatch):
    """
    Every retry must increment the counter zero times, not just the terminal
    attempt. A job that fails three times has produced no report.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "job_max_attempts", 3)

    attempts = {"n": 0}

    async def _boom(*a, **kw):
        attempts["n"] += 1
        raise RuntimeError("provider exploded")

    import app.llm

    monkeypatch.setattr(app.llm, "analyze_with_fallback", _boom)

    _, _, user_id = make_user(f"retry-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_usage, user_id, minutes=5.0, analyses=2))
    job_id = portal.call(_enqueue_direct, user_id, 2.0)

    # Attempts 1 and 2 requeue; the third is terminal.
    for _ in range(3):
        portal.call(run_one_job, settings)
        assert portal.call(_get_user, user_id).analyses_used_month == 2, (
            "a retry charged an analysis credit"
        )

    assert attempts["n"] == 3
    assert portal.call(_get_job, job_id).status == STATUS_FAILED
    user = portal.call(_get_user, user_id)
    assert user.analyses_used_month == 2
    assert user.minutes_used_month == pytest.approx(3.0), "minutes not refunded"


def test_failure_charges_no_analysis_and_refunds_minutes(portal, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "job_max_attempts", 1)

    async def _boom(*a, **kw):
        raise RuntimeError("provider exploded")

    import app.llm

    monkeypatch.setattr(app.llm, "analyze_with_fallback", _boom)

    _, _, user_id = make_user(f"fail-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_usage, user_id, minutes=5.0, analyses=3))
    job_id = portal.call(_enqueue_direct, user_id, 2.0)

    portal.call(run_one_job, settings)

    assert portal.call(_get_job, job_id).status == STATUS_FAILED
    user = portal.call(_get_user, user_id)
    assert user.minutes_used_month == pytest.approx(3.0), "minutes not refunded"
    assert user.analyses_used_month == 3, "a failed job consumed an analysis credit"


# ---------- Month rollover ----------


def test_rollover_resets_both_counters(client, portal):
    _, headers, user_id = make_user(f"roll-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_usage, user_id, minutes=9.0, analyses=7, month="2020-01"))

    body = client.get("/v1/me", headers=headers).json()
    assert body["minutes_used_month"] == 0.0
    assert body["analyses_used_month"] == 0


def test_stale_job_failing_this_month_refunds_nothing(portal, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "job_max_attempts", 1)

    async def _boom(*a, **kw):
        raise RuntimeError("boom")

    import app.llm

    monkeypatch.setattr(app.llm, "analyze_with_fallback", _boom)

    _, _, user_id = make_user(f"stale-{uuid.uuid4().hex[:6]}@example.com")
    job_id = portal.call(_enqueue_direct, user_id, 2.0, "2020-01")
    portal.call(partial(_set_usage, user_id, minutes=5.0, analyses=2))

    portal.call(run_one_job, settings)

    assert portal.call(_get_job, job_id).status == STATUS_FAILED
    user = portal.call(_get_user, user_id)
    assert user.minutes_used_month == pytest.approx(5.0), "stale refund applied"
    assert user.analyses_used_month == 2


def test_success_after_rollover_charges_the_current_month(portal, ok_provider):
    """A job from last month succeeding now counts against the live counter."""
    settings = get_settings()
    _, _, user_id = make_user(f"late-{uuid.uuid4().hex[:6]}@example.com")
    job_id = portal.call(_enqueue_direct, user_id, 1.0, "2020-01")
    portal.call(partial(_set_usage, user_id, analyses=2, minutes=0.0))

    portal.call(run_one_job, settings)

    assert portal.call(_get_job, job_id).status == STATUS_SUCCEEDED
    assert portal.call(_get_user, user_id).analyses_used_month == 3


# ---------- /v1/me ----------


def test_me_exposes_analyses_usage_and_limit(client, portal):
    settings = get_settings()
    _, headers, user_id = make_user(f"me-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_usage, user_id, analyses=4, minutes=2.0))

    body = client.get("/v1/me", headers=headers).json()
    assert body["analyses_used_month"] == 4
    assert body["analyses_limit"] == settings.pro_analyses_per_month
