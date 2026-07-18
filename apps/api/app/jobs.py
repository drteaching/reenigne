"""
Asynchronous analysis jobs.

/v1/analyze used to run the LLM call inside the request. A vision call over
dozens of screenshots takes minutes, which exceeds serverless execution
limits and leaves the caller holding an open connection the whole time.

Jobs decouple the two: the request enqueues and returns immediately, and a
runner executes the work out of band. The runner is triggered by whatever the
deployment provides — Vercel Cron, an external scheduler, or (for local dev
and long-running hosts) inline execution right after enqueue.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Text,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .config import Settings
from .db import Base, SessionLocal, User

# Terminal states never transition again.
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
TERMINAL_STATUSES = (STATUS_SUCCEEDED, STATUS_FAILED)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_QUEUED, index=True)

    target: Mapped[str] = mapped_column(String(512), default="")
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    prompt_template: Mapped[str] = mapped_column(String(64), default="teardown")
    model: Mapped[str] = mapped_column(String(128), default="")

    # The frames payload. Cleared once the job reaches a terminal state — it
    # is by far the largest column and is useless after the run.
    request_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    result_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_features_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Minutes debited at enqueue, refunded if the job ultimately fails.
    charged_minutes: Mapped[float] = mapped_column(Float, default=0.0)

    # Epoch seconds, not DateTime: SQLite hands back naive datetimes and
    # comparing those to tz-aware ones raises. Epoch floats compare correctly
    # on every backend.
    lease_expires_at: Mapped[float] = mapped_column(Float, default=0.0)
    lock_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ---------- Serialization ----------

    def public_dict(self) -> dict[str, Any]:
        """Client-facing view. Never exposes the request payload."""
        body: dict[str, Any] = {
            "job_id": self.id,
            "status": self.status,
            "target": self.target,
            "model": self.model,
            "attempts": self.attempts,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
        if self.status == STATUS_SUCCEEDED:
            body["markdown"] = self.result_markdown or ""
            body["features"] = (
                json.loads(self.result_features_json)
                if self.result_features_json
                else {}
            )
            body["model_used"] = self.model_used
        elif self.status == STATUS_FAILED:
            body["error"] = self.error or "Analysis failed"
        return body


# ---------- Queue operations ----------


async def create_job(
    session: AsyncSession,
    *,
    user: User,
    target: str,
    duration_seconds: float,
    prompt_template: str,
    model: str,
    frames: list[dict[str, Any]],
    charged_minutes: float,
) -> AnalysisJob:
    job = AnalysisJob(
        id=str(uuid.uuid4()),
        user_id=str(user.id),
        status=STATUS_QUEUED,
        target=target,
        duration_seconds=duration_seconds,
        prompt_template=prompt_template,
        model=model,
        request_json=json.dumps({"frames": frames}),
        charged_minutes=charged_minutes,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def get_job(
    session: AsyncSession, job_id: str, user_id: str
) -> AnalysisJob | None:
    """Scoped to the owner — job ids must not be cross-readable."""
    result = await session.execute(
        select(AnalysisJob).where(
            AnalysisJob.id == job_id, AnalysisJob.user_id == str(user_id)
        )
    )
    return result.scalar_one_or_none()


async def list_jobs(
    session: AsyncSession, user_id: str, limit: int = 20
) -> list[AnalysisJob]:
    result = await session.execute(
        select(AnalysisJob)
        .where(AnalysisJob.user_id == str(user_id))
        .order_by(AnalysisJob.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def count_active_jobs(session: AsyncSession, user_id: str) -> int:
    result = await session.execute(
        select(AnalysisJob).where(
            AnalysisJob.user_id == str(user_id),
            AnalysisJob.status.in_((STATUS_QUEUED, STATUS_RUNNING)),
        )
    )
    return len(list(result.scalars().all()))


def _runnable(now: float):
    """A job is runnable if it is queued, or running with a dead runner."""
    return (AnalysisJob.status == STATUS_QUEUED) | (
        (AnalysisJob.status == STATUS_RUNNING) & (AnalysisJob.lease_expires_at < now)
    )


async def select_claim_candidate(
    session: AsyncSession, now: float
) -> AnalysisJob | None:
    """Oldest runnable job. Split out from the claim so the race is testable."""
    result = await session.execute(
        select(AnalysisJob)
        .where(_runnable(now))
        .order_by(AnalysisJob.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def try_claim(
    session: AsyncSession, job_id: str, now: float, lease_seconds: int
) -> bool:
    """
    Attempt to take ownership of a specific job. True if this caller won.

    This is the concurrency guarantee. `select_claim_candidate` does not
    provide one: two runners can read the same candidate before either
    writes. Re-asserting the runnable predicate inside the UPDATE is what
    makes exactly one of them win, since the database applies the two updates
    serially and the loser no longer matches.
    """
    claimed = await session.execute(
        update(AnalysisJob)
        .where(AnalysisJob.id == job_id, _runnable(now))
        .values(
            status=STATUS_RUNNING,
            lock_token=str(uuid.uuid4()),
            lease_expires_at=now + lease_seconds,
            attempts=AnalysisJob.attempts + 1,
        )
    )
    await session.commit()
    return claimed.rowcount == 1


async def claim_next_job(
    session: AsyncSession, lease_seconds: int
) -> AnalysisJob | None:
    """
    Atomically take ownership of one runnable job, or return None.

    Deliberately avoids `FOR UPDATE SKIP LOCKED` so the same code path works
    on SQLite in tests.
    """
    for _ in range(5):  # bounded retry when another runner wins the race
        now = time.time()
        candidate = await select_claim_candidate(session, now)
        if candidate is None:
            return None

        if await try_claim(session, candidate.id, now, lease_seconds):
            await session.refresh(candidate)
            return candidate
        # Someone else got it; look for another.

    return None


async def complete_job(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    markdown: str,
    features: dict,
    model_used: str,
) -> None:
    job.status = STATUS_SUCCEEDED
    job.result_markdown = markdown
    job.result_features_json = json.dumps(features)
    job.model_used = model_used
    job.error = None
    job.request_json = None  # reclaim the frames payload
    job.finished_at = datetime.now(timezone.utc)
    job.lease_expires_at = 0.0
    job.lock_token = None
    await session.commit()


async def fail_job(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    error: str,
    max_attempts: int,
) -> bool:
    """
    Record a failed attempt. Returns True if the job is now terminal.

    Retries go back to `queued` and keep the payload; a terminal failure drops
    it and refunds the quota that was debited at enqueue.
    """
    job.error = error[:4000]
    job.lease_expires_at = 0.0
    job.lock_token = None

    if job.attempts < max_attempts:
        job.status = STATUS_QUEUED
        await session.commit()
        return False

    job.status = STATUS_FAILED
    job.request_json = None
    job.finished_at = datetime.now(timezone.utc)

    # The work never happened, so the user should not be billed for it.
    if job.charged_minutes:
        user = (
            await session.execute(select(User).where(User.id == job.user_id))
        ).scalar_one_or_none()
        if user:
            user.minutes_used_month = max(
                0.0, user.minutes_used_month - job.charged_minutes
            )
    await session.commit()
    return True


# ---------- Runner ----------


async def claim_job_by_id(
    session: AsyncSession, job_id: str, lease_seconds: int
) -> AnalysisJob | None:
    """Claim one specific job, if it is currently runnable."""
    now = time.time()
    token = str(uuid.uuid4())

    claimed = await session.execute(
        update(AnalysisJob)
        .where(
            AnalysisJob.id == job_id,
            (AnalysisJob.status == STATUS_QUEUED)
            | (
                (AnalysisJob.status == STATUS_RUNNING)
                & (AnalysisJob.lease_expires_at < now)
            ),
        )
        .values(
            status=STATUS_RUNNING,
            lock_token=token,
            lease_expires_at=now + lease_seconds,
            attempts=AnalysisJob.attempts + 1,
        )
    )
    await session.commit()
    if claimed.rowcount != 1:
        return None

    result = await session.execute(
        select(AnalysisJob).where(AnalysisJob.id == job_id)
    )
    return result.scalar_one_or_none()


async def _execute_claimed_job(
    session: AsyncSession, job: AnalysisJob, settings: Settings
) -> str:
    """Run an already-claimed job to a terminal (or retryable) state."""
    # Imported here: llm pulls in provider SDKs, and this module is imported
    # by db-only code paths that should not pay that cost.
    from .llm import analyze_with_fallback

    job_id = job.id
    try:
        payload = json.loads(job.request_json or "{}")
        markdown, features, model_used = await analyze_with_fallback(
            settings,
            prompt_template=job.prompt_template,
            model=job.model or settings.default_model,
            target=job.target,
            duration_seconds=job.duration_seconds,
            frames=payload.get("frames", []),
        )
    except Exception as e:
        await fail_job(
            session, job, error=str(e), max_attempts=settings.job_max_attempts
        )
        return job_id

    await complete_job(
        session,
        job,
        markdown=markdown,
        features=features,
        model_used=model_used,
    )
    return job_id


async def run_one_job(settings: Settings) -> str | None:
    """
    Claim and execute the oldest runnable job. Returns its id, or None if the
    queue is empty. Uses its own session so it is safe outside a request.
    """
    async with SessionLocal() as session:
        job = await claim_next_job(session, settings.job_lease_seconds)
        if job is None:
            return None
        return await _execute_claimed_job(session, job, settings)


async def run_job_by_id(settings: Settings, job_id: str) -> str | None:
    """
    Execute one specific job. Used by inline mode, where the caller means
    "run the job I just submitted" — not "run whatever is next in the queue",
    which would pick up some other user's older work.
    """
    async with SessionLocal() as session:
        job = await claim_job_by_id(session, job_id, settings.job_lease_seconds)
        if job is None:
            return None
        return await _execute_claimed_job(session, job, settings)


async def run_pending_jobs(settings: Settings, limit: int = 5) -> dict[str, Any]:
    """Drain up to `limit` jobs. Returns a summary for the trigger endpoint."""
    processed: list[str] = []
    for _ in range(limit):
        job_id = await run_one_job(settings)
        if job_id is None:
            break
        processed.append(job_id)
    return {"processed": len(processed), "job_ids": processed}
