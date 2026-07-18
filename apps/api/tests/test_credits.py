"""
Credit packs: a one-off balance consumed after the monthly allowance.

Credits differ from the monthly counter in three ways that all need cover:
they are purchased rather than granted, they are debited at enqueue rather
than charged on success (a finite balance has to be reserved), and they are
not period-scoped — a rollover must not touch them, and a refund must not be
guarded by the usage month the way the minutes refund is.
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


async def _set_state(user_id, analyses=0, credits=0, minutes=0.0, month=None):
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == user_id))).scalar_one()
        u.analyses_used_month = analyses
        u.credits = credits
        u.minutes_used_month = minutes
        u.usage_month = month if month is not None else _this_month()
        await s.commit()


async def _get_user(user_id) -> User:
    async with SessionLocal() as s:
        return (await s.execute(select(User).where(User.id == user_id))).scalar_one()


async def _get_job(job_id) -> AnalysisJob:
    async with SessionLocal() as s:
        return (
            await s.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
        ).scalar_one()


async def _enqueue_direct(user_id, charged_credits=0) -> str:
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
            charged_minutes=1.0,
        )
        if charged_credits:
            job.charged_credits = charged_credits
            await s.commit()
        return job.id


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
    async def _fake(settings, **kw):
        return "# Report", {"k": "v"}, "grok-4"

    import app.llm

    monkeypatch.setattr(app.llm, "analyze_with_fallback", _fake)


@pytest.fixture
def failing_provider(monkeypatch):
    async def _boom(*a, **kw):
        raise RuntimeError("provider exploded")

    import app.llm

    monkeypatch.setattr(app.llm, "analyze_with_fallback", _boom)


# ---------- Consumption order ----------


def test_credits_cover_the_job_once_monthly_is_exhausted(client, portal, ok_provider):
    settings = get_settings()
    _, headers, user_id = make_user(f"cred-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(
        partial(_set_state, user_id, analyses=settings.pro_analyses_per_month, credits=2)
    )

    resp = _submit(client, headers)
    assert resp.status_code == 202, resp.text

    user = portal.call(_get_user, user_id)
    assert user.credits == 1, "a credit should have been debited at enqueue"
    assert user.analyses_used_month == settings.pro_analyses_per_month

    job_id = resp.json()["job_id"]
    assert portal.call(_get_job, job_id).charged_credits == 1


def test_monthly_is_used_before_credits(client, portal, ok_provider):
    """Credits are a paid fallback, not the first thing spent."""
    _, headers, user_id = make_user(f"order-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_state, user_id, analyses=0, credits=5))

    job_id = _submit(client, headers).json()["job_id"]

    assert portal.call(_get_user, user_id).credits == 5, "credits spent too early"
    assert portal.call(_get_job, job_id).charged_credits == 0


def test_both_exhausted_returns_402_pointing_at_credit_purchase(
    client, portal, ok_provider
):
    settings = get_settings()
    _, headers, user_id = make_user(f"both-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(
        partial(_set_state, user_id, analyses=settings.pro_analyses_per_month, credits=0)
    )

    resp = _submit(client, headers)
    assert resp.status_code == 402
    detail = resp.json()["detail"]
    assert "/v1/billing/checkout-credits" in detail, (
        f"402 must point at credit purchase: {detail}"
    )
    assert "analys" in detail.lower()


def test_credit_funded_in_flight_work_does_not_consume_monthly_headroom(
    client, portal, ok_provider
):
    """
    At monthly limit-1 with a credit-funded job running, a monthly-funded
    submit must still be admitted. Counting credit-funded work toward the
    monthly in-flight term would charge the same job to both pools.
    """
    settings = get_settings()
    _, headers, user_id = make_user(f"inflight-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(
        partial(
            _set_state,
            user_id,
            analyses=settings.pro_analyses_per_month - 1,
            credits=3,
        )
    )
    portal.call(partial(_enqueue_direct, user_id, 1))  # credit-funded, in flight

    resp = _submit(client, headers)
    assert resp.status_code == 202, resp.text

    job_id = resp.json()["job_id"]
    assert portal.call(_get_job, job_id).charged_credits == 0, (
        "should have used the remaining monthly headroom, not a credit"
    )
    assert portal.call(_get_user, user_id).credits == 3


def test_monthly_funded_in_flight_work_still_consumes_headroom(
    client, portal, ok_provider
):
    """The counterpart: monthly-funded in-flight work does hold headroom."""
    settings = get_settings()
    _, headers, user_id = make_user(f"hold-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(
        partial(
            _set_state,
            user_id,
            analyses=settings.pro_analyses_per_month - 1,
            credits=0,
        )
    )
    portal.call(partial(_enqueue_direct, user_id, 0))  # monthly-funded, in flight

    resp = _submit(client, headers)
    assert resp.status_code == 402


# ---------- Refunds and completion ----------


def test_terminal_failure_refunds_the_credit_not_the_monthly_counter(
    portal, failing_provider, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "job_max_attempts", 1)

    _, _, user_id = make_user(f"refund-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_state, user_id, analyses=7, credits=2))
    job_id = portal.call(partial(_enqueue_direct, user_id, 1))
    portal.call(partial(_set_state, user_id, analyses=7, credits=1))  # as if debited

    portal.call(run_one_job, settings)

    assert portal.call(_get_job, job_id).status == STATUS_FAILED
    user = portal.call(_get_user, user_id)
    assert user.credits == 2, "credit not returned to the pool that funded the job"
    assert user.analyses_used_month == 7, "monthly counter must not be touched"


def test_credit_refund_ignores_month_rollover(portal, failing_provider, monkeypatch):
    """Credits are not period-scoped, unlike the minutes refund."""
    settings = get_settings()
    monkeypatch.setattr(settings, "job_max_attempts", 1)

    _, _, user_id = make_user(f"stale-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_state, user_id, credits=1, month="2020-01"))
    job_id = portal.call(partial(_enqueue_direct, user_id, 1))
    portal.call(partial(_set_state, user_id, credits=0))  # debited, now a new month

    portal.call(run_one_job, settings)

    assert portal.call(_get_job, job_id).status == STATUS_FAILED
    assert portal.call(_get_user, user_id).credits == 1


def test_credit_funded_success_does_not_charge_the_monthly_counter(
    portal, ok_provider
):
    settings = get_settings()
    _, _, user_id = make_user(f"paid-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_state, user_id, analyses=4, credits=1))
    job_id = portal.call(partial(_enqueue_direct, user_id, 1))

    portal.call(run_one_job, settings)

    assert portal.call(_get_job, job_id).status == STATUS_SUCCEEDED
    user = portal.call(_get_user, user_id)
    assert user.analyses_used_month == 4, "credit-funded job billed twice"


def test_monthly_funded_success_still_charges_the_counter(portal, ok_provider):
    settings = get_settings()
    _, _, user_id = make_user(f"mon-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_state, user_id, analyses=4, credits=1))
    portal.call(partial(_enqueue_direct, user_id, 0))

    portal.call(run_one_job, settings)

    user = portal.call(_get_user, user_id)
    assert user.analyses_used_month == 5
    assert user.credits == 1


# ---------- Rollover ----------


def test_credits_survive_month_rollover_while_counters_reset(client, portal):
    _, headers, user_id = make_user(f"roll-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(
        partial(_set_state, user_id, analyses=9, credits=4, minutes=8.0, month="2020-01")
    )

    body = client.get("/v1/me", headers=headers).json()
    assert body["analyses_used_month"] == 0
    assert body["minutes_used_month"] == 0.0
    assert body["credits"] == 4, "credits are not period-scoped and must persist"


def test_me_exposes_credits(client, portal):
    _, headers, user_id = make_user(f"me-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_state, user_id, credits=6))
    assert client.get("/v1/me", headers=headers).json()["credits"] == 6
