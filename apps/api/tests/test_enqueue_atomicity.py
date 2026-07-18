"""
The check-debit-enqueue sequence must be atomic per user.

Postgres only. Under READ COMMITTED, two concurrent transactions each
evaluate a count/quota check against their own snapshot and neither sees the
other's uncommitted insert, so a plain check-then-insert admits both. A
previous attempt used a single INSERT ... SELECT carrying the count in its
WHERE clause; that passed on SQLite and still admitted both on Postgres. The
fix is a row lock on the user, which serialises submissions per user.

SQLite has no row locks — SQLAlchemy omits FOR UPDATE there — so enqueue is
best-effort on the dev backend and these tests are skipped.
"""

import asyncio
import uuid
from functools import partial

import pytest
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionLocal, User
from app.jobs import AnalysisJob, enqueue_analysis
from conftest import make_user

pytestmark = pytest.mark.postgres_only


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


async def _set_usage(user_id, minutes=0.0, analyses=0):
    from datetime import datetime, timezone

    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == user_id))).scalar_one()
        u.minutes_used_month = minutes
        u.analyses_used_month = analyses
        u.usage_month = datetime.now(timezone.utc).strftime("%Y-%m")
        await s.commit()


async def _count_jobs(user_id) -> int:
    async with SessionLocal() as s:
        return len(
            (
                await s.execute(
                    select(AnalysisJob).where(AnalysisJob.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )


async def _get_user(user_id) -> User:
    async with SessionLocal() as s:
        return (
            await s.execute(select(User).where(User.id == user_id))
        ).scalar_one()


async def _concurrent_enqueues(user_id: str, n: int):
    """Run n enqueue attempts concurrently, each in its own session."""
    settings = get_settings()

    async def _one():
        async with SessionLocal() as session:
            user = (
                await session.execute(select(User).where(User.id == user_id))
            ).scalar_one()
            return await enqueue_analysis(
                session,
                user=user,
                settings=settings,
                target="App",
                duration_seconds=60,
                prompt_template="teardown",
                model="grok-4",
                frames=[{"index": 0, "image_b64": "AAAA"}],
            )

    return await asyncio.gather(*[_one() for _ in range(n)])


def test_concurrent_submits_at_the_last_monthly_credit_admit_exactly_one(portal):
    """Two submissions racing for the last slot of the monthly allowance."""
    settings = get_settings()
    _, _, user_id = make_user(f"race-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_usage, user_id, analyses=settings.pro_analyses_per_month - 1
    ))

    results = portal.call(_concurrent_enqueues, user_id, 2)

    accepted = [job for job, _ in results if job is not None]
    rejected = [reason for job, reason in results if job is None]
    assert len(accepted) == 1, (
        f"expected exactly one acceptance, got {len(accepted)}: {results}"
    )
    assert rejected and "analys" in rejected[0].detail.lower()
    assert rejected[0].status_code == 402
    assert portal.call(_count_jobs, user_id) == 1


def test_concurrent_submits_respect_the_active_job_cap(portal):
    """The same lock closes the count-then-insert race on the active cap."""
    settings = get_settings()
    _, _, user_id = make_user(f"cap-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_usage, user_id, analyses=0))

    results = portal.call(
        _concurrent_enqueues, user_id, settings.job_max_active_per_user + 3
    )

    accepted = [job for job, _ in results if job is not None]
    assert len(accepted) == settings.job_max_active_per_user, (
        f"cap is {settings.job_max_active_per_user}, admitted {len(accepted)}"
    )
    assert portal.call(_count_jobs, user_id) == settings.job_max_active_per_user


def test_concurrent_submits_debit_minutes_exactly_once_each(portal):
    """No lost updates on the minutes counter under concurrency."""
    _, _, user_id = make_user(f"debit-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_usage, user_id, minutes=0.0, analyses=0))

    results = portal.call(_concurrent_enqueues, user_id, 3)
    accepted = [job for job, _ in results if job is not None]

    user = portal.call(_get_user, user_id)
    expected = sum(j.charged_minutes for j in accepted)
    assert user.minutes_used_month == pytest.approx(expected), (
        "minutes debits were lost to a concurrent write"
    )


async def _set_credits(user_id, analyses, credits):
    from datetime import datetime, timezone

    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == user_id))).scalar_one()
        u.analyses_used_month = analyses
        u.credits = credits
        u.minutes_used_month = 0.0
        u.usage_month = datetime.now(timezone.utc).strftime("%Y-%m")
        await s.commit()


def test_concurrent_submits_at_the_last_purchased_credit_admit_exactly_one(portal):
    """
    Two submissions racing for a single remaining credit.

    The credit check and its decrement sit inside the same FOR UPDATE
    transaction as the job insert, so the loser must see the balance already
    spent. Without that lock both would read credits=1 and both would be
    admitted, overdrawing a purchased balance.
    """
    settings = get_settings()
    _, _, user_id = make_user(f"credrace-{uuid.uuid4().hex[:6]}@example.com")
    # Monthly exhausted, exactly one credit left.
    portal.call(
        partial(_set_credits, user_id, settings.pro_analyses_per_month, 1)
    )

    results = portal.call(_concurrent_enqueues, user_id, 2)

    accepted = [job for job, _ in results if job is not None]
    rejected = [r for job, r in results if job is None]
    assert len(accepted) == 1, (
        f"expected exactly one acceptance, got {len(accepted)}"
    )
    assert accepted[0].charged_credits == 1
    assert rejected[0].status_code == 402

    user = portal.call(_get_user, user_id)
    assert user.credits == 0, f"credit balance overdrawn or unspent: {user.credits}"
    assert portal.call(_count_jobs, user_id) == 1


def test_concurrent_submits_never_overdraw_a_multi_credit_balance(portal):
    """Five submissions, two credits, monthly exhausted -> exactly two run."""
    settings = get_settings()
    _, _, user_id = make_user(f"creddraw-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(
        partial(_set_credits, user_id, settings.pro_analyses_per_month, 2)
    )

    results = portal.call(_concurrent_enqueues, user_id, 5)
    accepted = [job for job, _ in results if job is not None]

    assert len(accepted) == 2, f"admitted {len(accepted)} on a balance of 2"
    assert portal.call(_get_user, user_id).credits == 0
