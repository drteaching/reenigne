"""
Stripe webhook: credit grants and replay safety.

Stripe redelivers events on any non-2xx and can redeliver on its own
schedule, so the handler has to be idempotent. A replayed
checkout.session.completed must not grant a second credit pack, and the
duplicate path must answer 200 — an error would make Stripe retry the very
event we have already applied.
"""

import uuid
from functools import partial

import pytest
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionLocal, User
from conftest import make_user


@pytest.fixture
def portal():
    from anyio.from_thread import start_blocking_portal

    with start_blocking_portal() as p:
        yield p


@pytest.fixture(autouse=True)
def webhook_configured(settings, monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")
    monkeypatch.setattr(settings, "credit_pack_size", 10)


async def _clear_events():
    from app.stripe_billing import StripeEvent

    async with SessionLocal() as s:
        await s.execute(delete(StripeEvent))
        await s.commit()


@pytest.fixture(autouse=True)
def clean_events(client, portal):
    portal.call(_clear_events)
    yield


async def _get_user(user_id) -> User:
    async with SessionLocal() as s:
        return (await s.execute(select(User).where(User.id == user_id))).scalar_one()


async def _set_credits(user_id, credits):
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == user_id))).scalar_one()
        u.credits = credits
        await s.commit()


def _fake_event(monkeypatch, event):
    """Bypass signature verification; we are testing handler behaviour."""
    import stripe

    monkeypatch.setattr(
        stripe.Webhook, "construct_event", staticmethod(lambda *a, **kw: event)
    )


def _payment_event(event_id, user_id):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "mode": "payment",
                "customer": "cus_test",
                "metadata": {"user_id": str(user_id)},
            }
        },
    }


def _post(client):
    return client.post(
        "/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=deadbeef"},
    )


def test_credit_pack_purchase_grants_credits(client, portal, monkeypatch):
    settings = get_settings()
    _, _, user_id = make_user(f"buy-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_credits, user_id, 0))

    _fake_event(monkeypatch, _payment_event(f"evt_{uuid.uuid4().hex}", user_id))
    assert _post(client).status_code == 200

    assert portal.call(_get_user, user_id).credits == settings.credit_pack_size


def test_replayed_event_credits_exactly_once(client, portal, monkeypatch):
    settings = get_settings()
    _, _, user_id = make_user(f"replay-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_credits, user_id, 0))

    event = _payment_event(f"evt_{uuid.uuid4().hex}", user_id)
    _fake_event(monkeypatch, event)

    first = _post(client)
    second = _post(client)
    third = _post(client)

    assert first.status_code == 200
    assert portal.call(_get_user, user_id).credits == settings.credit_pack_size, (
        "a replayed event granted a second pack"
    )
    assert second.status_code == 200, "duplicate must be acked, not errored"
    assert third.status_code == 200
    assert second.json().get("duplicate") is True


def test_duplicate_path_never_returns_an_error_status(client, portal, monkeypatch):
    """
    Explicitly pinned: a non-2xx here makes Stripe retry an event we have
    already applied, forever.
    """
    _, _, user_id = make_user(f"ack-{uuid.uuid4().hex[:6]}@example.com")
    event = _payment_event(f"evt_{uuid.uuid4().hex}", user_id)
    _fake_event(monkeypatch, event)

    _post(client)
    for _ in range(3):
        resp = _post(client)
        assert resp.status_code == 200, resp.text


def test_distinct_events_each_grant(client, portal, monkeypatch):
    settings = get_settings()
    _, _, user_id = make_user(f"two-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_credits, user_id, 0))

    for _ in range(2):
        _fake_event(monkeypatch, _payment_event(f"evt_{uuid.uuid4().hex}", user_id))
        assert _post(client).status_code == 200

    assert portal.call(_get_user, user_id).credits == 2 * settings.credit_pack_size


def test_subscription_mode_does_not_grant_credits(client, portal, monkeypatch):
    """checkout.session.completed also fires for subscriptions."""
    _, _, user_id = make_user(f"sub-{uuid.uuid4().hex[:6]}@example.com")
    portal.call(partial(_set_credits, user_id, 0))

    event = {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "mode": "subscription",
                "customer": "cus_test",
                "subscription": "sub_123",
                "metadata": {"user_id": str(user_id)},
            }
        },
    }
    _fake_event(monkeypatch, event)
    assert _post(client).status_code == 200
    assert portal.call(_get_user, user_id).credits == 0


def test_unknown_user_is_acked_without_crashing(client, monkeypatch):
    """A payment we cannot attribute must not wedge Stripe's retry queue."""
    event = _payment_event(f"evt_{uuid.uuid4().hex}", uuid.uuid4())
    _fake_event(monkeypatch, event)
    assert _post(client).status_code == 200
