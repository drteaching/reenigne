"""
Concurrency and billing edge cases around enqueue/refund.

Both defects here are invisible in single-threaded, same-month tests, which
is exactly why they need explicit ones.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionLocal, User
from app.jobs import (
    STATUS_FAILED,
    AnalysisJob,
    count_active_jobs,
    create_job,
    fail_job,
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


async def _set_usage(user_id: str, minutes: float, month: str) -> None:
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == user_id))).scalar_one()
        u.minutes_used_month = minutes
        u.usage_month = month
        await s.commit()


async def _get_user(user_id: str) -> User:
    async with SessionLocal() as s:
        return (
            await s.execute(select(User).where(User.id == user_id))
        ).scalar_one()


async def _enqueue(user_id: str, charged: float, month: str | None = None) -> str:
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


async def _get_job(job_id: str) -> AnalysisJob:
    async with SessionLocal() as s:
        return (
            await s.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
        ).scalar_one()


# ---------- Refund across a month boundary ----------


def test_refund_applies_within_the_same_month(portal):
    settings = get_settings()
    _, _, user_id = make_user(f"same-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(_set_usage, user_id, 5.0, _this_month())
    job_id = portal.call(_enqueue, user_id, 2.0)

    async def _fail_terminally():
        async with SessionLocal() as s:
            job = (
                await s.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
            ).scalar_one()
            job.attempts = settings.job_max_attempts
            await s.commit()
            await fail_job(
                s, job, error="boom", max_attempts=settings.job_max_attempts
            )

    portal.call(_fail_terminally)

    user = portal.call(_get_user, user_id)
    assert user.minutes_used_month == pytest.approx(3.0)


def test_refund_skipped_after_month_rollover(portal):
    """
    A job enqueued last month must not be refunded against this month's
    counter. The debit it is refunding was already wiped by the monthly
    reset, so refunding would credit the user minutes they never spent —
    and repeated failures could drive the counter to zero every month.
    """
    settings = get_settings()
    _, _, user_id = make_user(f"roll-{uuid.uuid4().hex[:6]}@example.com")

    # Job belongs to a previous month; the user has since rolled over.
    job_id = portal.call(_enqueue, user_id, 2.0, "2020-01")
    portal.call(_set_usage, user_id, 5.0, _this_month())

    async def _fail_terminally():
        async with SessionLocal() as s:
            job = (
                await s.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
            ).scalar_one()
            job.attempts = settings.job_max_attempts
            await s.commit()
            await fail_job(
                s, job, error="boom", max_attempts=settings.job_max_attempts
            )

    portal.call(_fail_terminally)

    user = portal.call(_get_user, user_id)
    assert user.minutes_used_month == pytest.approx(5.0), (
        "a stale job refunded against the current month's usage"
    )
    assert portal.call(_get_job, job_id).status == STATUS_FAILED


def test_enqueue_records_the_usage_month(portal):
    _, _, user_id = make_user(f"month-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(_set_usage, user_id, 0.0, _this_month())
    job_id = portal.call(_enqueue, user_id, 1.0)
    assert portal.call(_get_job, job_id).usage_month == _this_month()


# ---------- Active-job cap ----------


def test_cap_counts_only_active_jobs(portal):
    """Terminal jobs must not occupy a slot."""
    _, _, user_id = make_user(f"cap-{uuid.uuid4().hex[:6]}@example.com")
    job_id = portal.call(_enqueue, user_id, 1.0)

    async def _finish():
        async with SessionLocal() as s:
            job = (
                await s.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
            ).scalar_one()
            job.status = STATUS_FAILED
            await s.commit()
            return await count_active_jobs(s, user_id)

    assert portal.call(_finish) == 0
