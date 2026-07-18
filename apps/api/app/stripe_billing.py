"""Stripe Checkout, Portal, and webhook helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import stripe
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .db import User


def configure_stripe(settings: Settings) -> None:
    stripe.api_key = settings.stripe_secret_key


async def ensure_customer(session: AsyncSession, user: User, settings: Settings) -> str:
    configure_stripe(settings)
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = await stripe.Customer.create_async(
        email=user.email, metadata={"user_id": str(user.id)}
    )
    user.stripe_customer_id = customer.id
    await session.commit()
    return customer.id


async def create_checkout_session(
    session: AsyncSession, user: User, settings: Settings
) -> str:
    if not settings.stripe_secret_key or not settings.stripe_price_id:
        raise RuntimeError("Stripe is not configured")
    customer_id = await ensure_customer(session, user, settings)
    checkout = await stripe.checkout.Session.create_async(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
        metadata={"user_id": str(user.id)},
        allow_promotion_codes=True,
    )
    return checkout.url


async def create_portal_session(
    session: AsyncSession, user: User, settings: Settings
) -> str:
    if not settings.stripe_secret_key:
        raise RuntimeError("Stripe is not configured")
    customer_id = await ensure_customer(session, user, settings)
    portal = await stripe.billing_portal.Session.create_async(
        customer=customer_id,
        return_url="https://reenigne.dev/account",
    )
    return portal.url


async def apply_subscription_update(
    session: AsyncSession,
    *,
    customer_id: str,
    status: str,
    subscription_id: str | None,
) -> None:
    result = await session.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return
    user.subscription_status = status
    user.subscription_id = subscription_id
    user.plan = "pro" if status in ("active", "trialing") else "free"
    await session.commit()


def reset_usage_if_needed(user: User) -> None:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    if user.usage_month != month:
        user.usage_month = month
        user.minutes_used_month = 0.0
        user.analyses_used_month = 0


def quota_rejection(
    user: User, settings: Settings, *, in_flight_analyses: int = 0
) -> str | None:
    """
    Which limit, if any, blocks more work right now. None if within quota.

    `in_flight_analyses` counts queued/running jobs. The analysis credit is
    charged on success, not reserved at enqueue, so without counting work
    already in flight a user at limit-1 could submit several jobs that each
    pass the check and collectively overshoot.

    Callers must have run reset_usage_if_needed first so a new month starts
    from zero.
    """
    if user.minutes_used_month >= settings.pro_minutes_per_month:
        return (
            f"Monthly quota exhausted "
            f"({user.minutes_used_month:.1f}/{settings.pro_minutes_per_month} "
            f"minutes). Resets at the start of next month."
        )

    used = user.analyses_used_month + in_flight_analyses
    if used >= settings.pro_analyses_per_month:
        in_flight_note = (
            f" ({in_flight_analyses} in progress)" if in_flight_analyses else ""
        )
        return (
            f"Monthly analyses quota exhausted "
            f"({user.analyses_used_month}/{settings.pro_analyses_per_month} "
            f"analyses{in_flight_note}). Resets at the start of next month."
        )
    return None


def require_quota_remaining(
    user: User, settings: Settings, *, in_flight_analyses: int = 0
) -> None:
    """Reject before doing billable work, naming the limit that was hit."""
    rejection = quota_rejection(
        user, settings, in_flight_analyses=in_flight_analyses
    )
    if rejection:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=rejection
        )
