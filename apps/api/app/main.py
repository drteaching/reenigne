"""reenigne cloud API — auth, Stripe, Whisper + LLM proxies."""

from __future__ import annotations

import logging
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_active_subscription,
    verify_password,
)
from .config import Settings, get_settings
from .db import User, get_session, get_user_by_email, init_db, new_local_user_id
from .jobs import (
    enqueue_analysis,
    get_job,
    list_jobs,
    run_job_by_id,
    run_pending_jobs,
)
from .llm import analyze_with_fallback, transcribe_whisper
from .stripe_billing import (
    StripeEvent,
    apply_subscription_update,
    create_checkout_session,
    create_credit_checkout_session,
    create_portal_session,
    grant_credits,
    require_quota_remaining,
    reset_usage_if_needed,
)
from .supabase_auth import supabase_login, supabase_signup


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings().validate_runtime()
    await init_db()
    yield


# Billing events that need operator attention are logged here so they can be
# alerted on independently of general request noise.
billing_log = logging.getLogger("app.billing")

app = FastAPI(title="reenigne API", version="0.2.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Schemas ----------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    email: str
    subscription_status: str
    plan: str
    minutes_used_month: float
    minutes_limit: int
    analyses_used_month: int
    analyses_limit: int
    credits: int
    max_frames_per_session: int


class FramePayload(BaseModel):
    index: int
    timestamp_seconds: float = 0
    narration: str = ""
    ocr_text: str = ""
    image_b64: str
    media_type: str = "image/jpeg"


class AnalyzeRequest(BaseModel):
    target: str
    duration_seconds: float = 0
    prompt_template: str = "teardown"
    model: str = "grok-4"
    frames: list[FramePayload]


class AnalyzeResponse(BaseModel):
    markdown: str
    features: dict[str, Any]
    model_used: str


class CheckoutResponse(BaseModel):
    url: str


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str
    poll_url: str


# ---------- Auth ----------


@app.get("/health")
async def health():
    return {"ok": True, "service": "reenigne-api"}


@app.post("/v1/auth/register", response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    if settings.use_supabase:
        try:
            token = await supabase_signup(settings, body.email, body.password)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return TokenResponse(access_token=token)

    existing = await get_user_by_email(session, body.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        id=new_local_user_id(),
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        usage_month=datetime.now(timezone.utc).strftime("%Y-%m"),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token)


@app.post("/v1/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    if settings.use_supabase:
        try:
            token = await supabase_login(settings, body.email, body.password)
        except Exception as e:
            raise HTTPException(status_code=401, detail=str(e))
        return TokenResponse(access_token=token)

    user = await get_user_by_email(session, body.email)
    if not user or not user.password_hash or not verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(user.id, user.email))


@app.get("/v1/me", response_model=MeResponse)
async def me(
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    reset_usage_if_needed(user)
    await session.commit()
    return MeResponse(
        email=user.email,
        subscription_status=user.subscription_status,
        plan=user.plan,
        minutes_used_month=user.minutes_used_month,
        minutes_limit=settings.pro_minutes_per_month,
        analyses_used_month=user.analyses_used_month,
        analyses_limit=settings.pro_analyses_per_month,
        credits=user.credits,
        max_frames_per_session=settings.pro_max_frames_per_session,
    )


# ---------- Billing ----------


@app.post("/v1/billing/checkout", response_model=CheckoutResponse)
async def billing_checkout(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    try:
        url = await create_checkout_session(session, user, settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return CheckoutResponse(url=url)


@app.post("/v1/billing/checkout-credits", response_model=CheckoutResponse)
async def billing_checkout_credits(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """
    One-off credit pack purchase (Stripe mode="payment").

    Credits are granted by the webhook, not here — the session URL only means
    the user was sent to Stripe, and treating that as payment would hand out
    credits to anyone who abandoned checkout.
    """
    if not settings.stripe_credit_pack_price_id:
        raise HTTPException(status_code=404, detail="Credit packs are not available")
    try:
        url = await create_credit_checkout_session(session, user, settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return CheckoutResponse(url=url)


@app.post("/v1/billing/portal", response_model=CheckoutResponse)
async def billing_portal(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    try:
        url = await create_portal_session(session, user, settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return CheckoutResponse(url=url)


@app.post("/v1/billing/webhook")
async def stripe_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    import stripe

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=500, detail="Webhook not configured")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, settings.stripe_webhook_secret
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    etype = event["type"]
    data = event["data"]["object"]

    # Replay guard. Stripe redelivers on any non-2xx and on its own schedule,
    # so every handler below must be applied at most once. Claiming the event
    # id and applying the effect share one transaction: a mid-processing
    # failure rolls back the marker too, so Stripe's retry still lands.
    session.add(StripeEvent(id=str(event["id"]), type=etype))
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        # 200, deliberately. A non-2xx here would make Stripe retry an event
        # we have already applied — forever.
        return {"received": True, "duplicate": True}

    if etype == "checkout.session.completed":
        customer_id = data.get("customer")
        # The same event type fires for subscriptions and one-off payments.
        if data.get("mode") == "payment":
            granted = await grant_credits(
                session,
                amount=settings.credit_pack_size,
                user_id=(data.get("metadata") or {}).get("user_id"),
                customer_id=customer_id,
            )
            if not granted:
                # Money arrived and no credits were granted. Acking is still
                # right — retrying cannot attribute it either — but this must
                # not pass silently, so it is logged loudly enough to alert
                # on. The marker is deliberately grep-able and should be rare.
                billing_log.error(
                    "STRIPE_UNATTRIBUTED_PAYMENT event_id=%s session_id=%s "
                    "customer_id=%s metadata_user_id=%s — payment succeeded "
                    "but no matching user was found; credits NOT granted, "
                    "manual reconciliation required",
                    event.get("id"),
                    data.get("id"),
                    customer_id,
                    (data.get("metadata") or {}).get("user_id"),
                )
                await session.commit()
                return {"received": True, "unattributed": True}
        elif customer_id:
            await apply_subscription_update(
                session,
                customer_id=customer_id,
                status="active",
                subscription_id=data.get("subscription"),
            )
    elif etype in (
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        customer_id = data.get("customer")
        status_val = data.get("status", "canceled")
        if etype == "customer.subscription.deleted":
            status_val = "canceled"
        if customer_id:
            await apply_subscription_update(
                session,
                customer_id=customer_id,
                status=status_val,
                subscription_id=data.get("id"),
            )

    await session.commit()
    return {"received": True}


# ---------- Gated AI proxies ----------


@app.post("/v1/transcribe")
async def transcribe(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: UploadFile = File(...),
):
    require_active_subscription(user)
    reset_usage_if_needed(user)
    require_quota_remaining(user, settings)

    # Read in chunks so an oversized upload is rejected before we have
    # buffered the whole thing in memory.
    limit = settings.max_audio_upload_bytes
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"Audio file too large (limit {limit // (1024 * 1024)} MB)",
            )
        chunks.append(chunk)
    audio = b"".join(chunks)

    try:
        segments = await transcribe_whisper(
            settings, audio, file.filename or "audio.wav"
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Whisper failed: {e}")

    # Rough usage: estimate minutes from last segment end
    if segments:
        user.minutes_used_month += segments[-1]["end"] / 60.0
        await session.commit()

    return {"segments": segments}


def _downsample_frames(frames: list, limit: int) -> list:
    """Evenly sample across the session so the walkthrough keeps its shape."""
    if len(frames) <= limit:
        return frames
    step = len(frames) / limit
    return [frames[int(i * step)] for i in range(limit)]


def _analysis_cost_minutes(duration_seconds: float) -> float:
    return max(duration_seconds / 60.0 * 0.1, 0.1)


@app.post(
    "/v1/analyze/jobs",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_analysis_job(
    body: AnalyzeRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """
    Enqueue an analysis and return immediately.

    The provider call runs out of band, so neither the request duration nor
    the serverless execution limit bounds how long analysis may take.

    Exception: with JOB_RUN_INLINE=true this call blocks for the *entire*
    analysis — minutes — and returns only once the job is terminal. That
    defeats the purpose of the queue and exists purely so local development
    needs no separate runner process. It is dev-only: never enable it on a
    platform with a request timeout. For a long-running host use the
    standalone runner (python -m app.runner_loop) instead.
    """
    require_active_subscription(user)

    if not body.frames:
        raise HTTPException(status_code=400, detail="No frames supplied")

    frames = _downsample_frames(body.frames, settings.pro_max_frames_per_session)

    # Quota checks, the minutes debit and the insert all happen inside one
    # transaction holding a row lock on the user, so concurrent submissions
    # cannot both slip past a limit.
    job, rejection = await enqueue_analysis(
        session,
        user=user,
        settings=settings,
        target=body.target,
        duration_seconds=body.duration_seconds,
        prompt_template=body.prompt_template,
        model=body.model or settings.default_model,
        frames=[f.model_dump() for f in frames],
    )
    if rejection is not None:
        raise HTTPException(
            status_code=rejection.status_code, detail=rejection.detail
        )

    if settings.job_run_inline:
        await run_job_by_id(settings, job.id)

    return JobSubmitResponse(
        job_id=job.id,
        status=job.status,
        poll_url=f"/v1/analyze/jobs/{job.id}",
    )


@app.get("/v1/analyze/jobs/{job_id}")
async def get_analysis_job(
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    job = await get_job(session, job_id, str(user.id))
    if job is None:
        # 404 rather than 403 for another user's job — do not confirm it exists.
        raise HTTPException(status_code=404, detail="Job not found")
    return job.public_dict()


@app.get("/v1/analyze/jobs")
async def list_analysis_jobs(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    jobs = await list_jobs(session, str(user.id))
    return {"jobs": [j.public_dict() for j in jobs]}


@app.api_route("/v1/internal/jobs/run", methods=["GET", "POST"])
async def run_jobs(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
):
    """
    Drain the queue. Triggered by Vercel Cron or an external scheduler.

    Authenticated by a shared secret rather than a user token — there is no
    user in this context. Accepts GET as well as POST, and takes the secret
    either as a bearer token or a custom header, because Vercel Cron issues a
    GET with `Authorization: Bearer $CRON_SECRET` and cannot be configured to
    do otherwise.
    """
    if not settings.job_runner_secret:
        raise HTTPException(status_code=404, detail="Not found")

    supplied = request.headers.get("x-job-runner-secret", "")
    if not supplied:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            supplied = auth[7:]

    # Constant-time: a plain == leaks the secret through timing.
    if not secrets.compare_digest(supplied, settings.job_runner_secret):
        raise HTTPException(status_code=401, detail="Invalid runner credentials")

    # Budget measured from now — this request IS the invocation, so the
    # platform's execution clock starts here.
    deadline = time.monotonic() + settings.job_runner_max_seconds
    return await run_pending_jobs(settings, deadline=deadline)


@app.post("/v1/analyze", response_model=AnalyzeResponse, deprecated=True)
async def analyze(
    body: AnalyzeRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """
    Deprecated: runs the provider call inside the request, so it can exceed
    the serverless execution limit on anything but a small session. Kept for
    older clients. New callers should use POST /v1/analyze/jobs.
    """
    require_active_subscription(user)
    reset_usage_if_needed(user)
    require_quota_remaining(user, settings)

    body.frames = _downsample_frames(body.frames, settings.pro_max_frames_per_session)

    try:
        markdown, features, model_used = await analyze_with_fallback(
            settings,
            prompt_template=body.prompt_template,
            model=body.model or settings.default_model,
            target=body.target,
            duration_seconds=body.duration_seconds,
            frames=[f.model_dump() for f in body.frames],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    user.minutes_used_month += _analysis_cost_minutes(body.duration_seconds)
    await session.commit()

    return AnalyzeResponse(
        markdown=markdown, features=features, model_used=model_used
    )


# Dev helper: mark user as subscribed. Requires an explicit opt-in flag —
# never infer "we must be in dev" from some other setting being absent.
@app.post("/v1/dev/activate")
async def dev_activate(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    if not settings.enable_dev_endpoints or settings.stripe_secret_key:
        raise HTTPException(status_code=404, detail="Not found")
    user.subscription_status = "active"
    user.plan = "pro"
    await session.commit()
    return {"ok": True, "subscription_status": "active"}
