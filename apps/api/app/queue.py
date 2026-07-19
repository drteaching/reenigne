"""
Shared claim/lease mechanics for every job queue.

Extracted from app/jobs.py when feedback triage became a second job type.
Deliberately generic rather than duplicated: the correctness argument below
took two attempts to get right on Postgres, and a forked copy would drift.

Any model used here must provide `status`, `lease_expires_at`, `attempts` and
`created_at`. It must NOT be assumed to carry billing columns — feedback
triage rows deliberately have none, which is why triage lives in its own
table rather than behind a job_type discriminator.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
TERMINAL_STATUSES = (STATUS_SUCCEEDED, STATUS_FAILED)

JobModel = TypeVar("JobModel")


def runnable_clause(model: Any, now: float):
    """Queued, or running with a lease that has lapsed (dead runner)."""
    return (model.status == STATUS_QUEUED) | (
        (model.status == STATUS_RUNNING) & (model.lease_expires_at < now)
    )


async def select_claim_candidate(
    session: AsyncSession, model: Any, now: float
) -> Any | None:
    """
    Oldest runnable row. Split from the claim so the race is testable: this
    provides no exclusivity on its own, and two runners can both see the same
    candidate.
    """
    result = await session.execute(
        select(model).where(runnable_clause(model, now)).order_by(model.created_at).limit(1)
    )
    return result.scalar_one_or_none()


async def peek_oldest_runnable_at(
    session: AsyncSession, model: Any, now: float
) -> datetime | None:
    """
    Age of the oldest runnable row, without claiming it.

    Used to pick between queues: the drain claims from whichever queue holds
    the older job, which is what stops a cheap queue starving behind a busy
    one (or vice versa) when the batch size is 1.
    """
    result = await session.execute(
        select(model.created_at)
        .where(runnable_clause(model, now))
        .order_by(model.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def try_claim(
    session: AsyncSession, model: Any, job_id: str, now: float, lease_seconds: int
) -> bool:
    """
    Attempt to take ownership of a specific row. True if this caller won.

    This is the concurrency guarantee. Re-asserting the runnable predicate
    inside the UPDATE is what makes exactly one of two racing runners win: the
    database applies the updates serially and the loser no longer matches.
    Deliberately not FOR UPDATE SKIP LOCKED, so the identical path runs on
    SQLite in tests.
    """
    claimed = await session.execute(
        update(model)
        .where(model.id == job_id, runnable_clause(model, now))
        .values(
            status=STATUS_RUNNING,
            lock_token=str(uuid.uuid4()),
            lease_expires_at=now + lease_seconds,
            attempts=model.attempts + 1,
        )
    )
    await session.commit()
    return claimed.rowcount == 1


async def claim_next(
    session: AsyncSession, model: Any, lease_seconds: int
) -> Any | None:
    """Atomically take ownership of one runnable row, or return None."""
    for _ in range(5):  # bounded retry when another runner wins the race
        now = time.time()
        candidate = await select_claim_candidate(session, model, now)
        if candidate is None:
            return None
        if await try_claim(session, model, candidate.id, now, lease_seconds):
            await session.refresh(candidate)
            return candidate
    return None


async def claim_by_id(
    session: AsyncSession, model: Any, job_id: str, lease_seconds: int
) -> Any | None:
    """Claim one specific row, if it is currently runnable."""
    now = time.time()
    if not await try_claim(session, model, job_id, now, lease_seconds):
        return None
    result = await session.execute(select(model).where(model.id == job_id))
    return result.scalar_one_or_none()
