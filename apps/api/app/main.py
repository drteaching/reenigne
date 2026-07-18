"""reenigne cloud API — auth, Stripe, Whisper + LLM proxies."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
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
from .llm import analyze_with_fallback, transcribe_whisper
from .stripe_billing import (
    apply_subscription_update,
    create_checkout_session,
    create_portal_session,
    require_quota_remaining,
    reset_usage_if_needed,
)
from .supabase_auth import supabase_login, supabase_signup


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings().validate_runtime()
    await init_db()
    yield


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

    if etype == "checkout.session.completed":
        customer_id = data.get("customer")
        sub_id = data.get("subscription")
        if customer_id:
            await apply_subscription_update(
                session,
                customer_id=customer_id,
                status="active",
                subscription_id=sub_id,
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


@app.post("/v1/analyze", response_model=AnalyzeResponse)
async def analyze(
    body: AnalyzeRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    require_active_subscription(user)
    reset_usage_if_needed(user)
    require_quota_remaining(user, settings)

    if len(body.frames) > settings.pro_max_frames_per_session:
        # Evenly downsample server-side
        step = len(body.frames) / settings.pro_max_frames_per_session
        body.frames = [
            body.frames[int(i * step)]
            for i in range(settings.pro_max_frames_per_session)
        ]

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

    user.minutes_used_month += max(body.duration_seconds / 60.0 * 0.1, 0.1)
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
