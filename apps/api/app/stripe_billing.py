"""Stripe Checkout, Portal, and webhook helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import stripe
from fastapi import HTTPException, status
from sqlalchemy import DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .config import Settings
from .db import Base, User, is_uuid


class StripeEvent(Base):
    """
    Stripe event ids we have already applied.

    Stripe redelivers on any non-2xx and on its own schedule, so handlers must
    be idempotent. The id is the primary key: a replay collides on insert and
    the handler returns early. Recorded in the same transaction as the effect,
    so a mid-processing failure rolls back both and Stripe's retry still lands.
    """

    __tablename__ = "stripe_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(128), default="")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


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
    # No commit: the webhook commits the subscription change and its replay
    # marker together.


def reset_usage_if_needed(user: User) -> None:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    if user.usage_month != month:
        user.usage_month = month
        user.minutes_used_month = 0.0
        user.analyses_used_month = 0


POOL_MONTHLY = "monthly"
POOL_CREDIT = "credit"

CREDIT_PURCHASE_PATH = "/v1/billing/checkout-credits"


def select_funding_pool(
    user: User, settings: Settings, *, in_flight_monthly: int = 0
) -> tuple[str | None, str | None]:
    """
    Decide which pool pays for the next analysis: (pool, rejection).

    Monthly allowance first, then purchased credits — credits are a paid
    fallback and must not be spent while free headroom remains.

    `in_flight_monthly` counts only *monthly-funded* queued/running jobs. The
    monthly credit is charged on success rather than reserved, so work already
    in flight has to hold its headroom or several submissions would each pass
    the check and collectively overshoot. Credit-funded work is excluded: it
    has already been paid for out of the other pool, and counting it here
    would charge one job against both.

    Callers must have run reset_usage_if_needed first so a new month starts
    from zero.
    """
    # Secondary abuse guard, not the binding constraint.
    if user.minutes_used_month >= settings.pro_minutes_per_month:
        return None, (
            f"Monthly processing limit reached "
            f"({user.minutes_used_month:.0f}/{settings.pro_minutes_per_month} "
            f"minutes). Resets at the start of next month."
        )

    monthly_used = user.analyses_used_month + in_flight_monthly
    if monthly_used < settings.pro_analyses_per_month:
        return POOL_MONTHLY, None

    if user.credits > 0:
        return POOL_CREDIT, None

    in_flight_note = (
        f", {in_flight_monthly} in progress" if in_flight_monthly else ""
    )
    return None, (
        f"Monthly analyses quota exhausted "
        f"({user.analyses_used_month}/{settings.pro_analyses_per_month} "
        f"analyses{in_flight_note}) and no credits remaining. "
        f"Buy a credit pack at {CREDIT_PURCHASE_PATH}, or wait for the "
        f"allowance to reset at the start of next month."
    )


def require_quota_remaining(
    user: User, settings: Settings, *, in_flight_monthly: int = 0
) -> None:
    """Reject before doing billable work, naming the limit that was hit."""
    _, rejection = select_funding_pool(
        user, settings, in_flight_monthly=in_flight_monthly
    )
    if rejection:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=rejection
        )


# ---------- Credit packs ----------


async def create_credit_checkout_session(
    session: AsyncSession, user: User, settings: Settings
) -> str:
    if not settings.stripe_secret_key or not settings.stripe_credit_pack_price_id:
        raise RuntimeError("Credit packs are not configured")
    customer_id = await ensure_customer(session, user, settings)
    checkout = await stripe.checkout.Session.create_async(
        customer=customer_id,
        mode="payment",
        line_items=[
            {"price": settings.stripe_credit_pack_price_id, "quantity": 1}
        ],
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
        # The webhook attributes the purchase by this, falling back to the
        # customer id.
        metadata={"user_id": str(user.id), "kind": "credit_pack"},
    )
    return checkout.url


async def grant_credits(
    session: AsyncSession,
    *,
    amount: int,
    user_id: str | None = None,
    customer_id: str | None = None,
) -> bool:
    """
    Add credits to whichever user the purchase belongs to. False if unknown.

    Does not commit — the caller owns the transaction, so the grant and the
    webhook's replay marker land together or not at all.
    """
    user = None
    if user_id and is_uuid(user_id):
        user = (
            await session.execute(
                select(User)
                .where(User.id == str(user_id))
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
    if user is None and customer_id:
        user = (
            await session.execute(
                select(User)
                .where(User.stripe_customer_id == customer_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    if user is None:
        return False

    user.credits += amount
    return True
