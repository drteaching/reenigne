"""
Rate limiting on the unauthenticated auth routes.

Deliberately best-effort: the window lives in process memory, so it does not
span serverless instances. These tests pin the behaviour it does provide —
a burst from one address against one instance is refused — and the limitation
is documented in app/ratelimit.py rather than papered over.
"""

import uuid

import pytest

from app.config import get_settings
from app.ratelimit import reset


@pytest.fixture(autouse=True)
def tight_limit(settings, monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 3)
    reset()
    yield
    reset()


def _login(client, email="nobody@example.com"):
    return client.post(
        "/v1/auth/login", json={"email": email, "password": "wrongpassword1"}
    )


def _register(client):
    return client.post(
        "/v1/auth/register",
        json={"email": f"rl{uuid.uuid4().hex[:8]}@example.com", "password": "hunter2hunter2"},
    )


def test_login_burst_is_refused_after_the_limit(client):
    settings = get_settings()
    for _ in range(settings.auth_rate_limit_per_minute):
        assert _login(client).status_code == 401

    resp = _login(client)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_failed_password_still_consumes_an_attempt(client):
    """
    Counted before the password check, so guessing is not free. Otherwise a
    limiter that only counts successes protects nothing.
    """
    for _ in range(3):
        assert _login(client).status_code == 401
    assert _login(client).status_code == 429


@pytest.mark.sqlite_only
def test_register_burst_is_refused(client):
    """
    sqlite_only: completing a registration inserts straight into profiles,
    which the auth.users foreign key forbids on the Supabase schema. The
    limiter itself is backend-independent — the login tests cover it on both.
    """
    for _ in range(3):
        assert _register(client).status_code in (200, 400)
    assert _register(client).status_code == 429


@pytest.mark.sqlite_only
def test_login_and_register_have_separate_allowances(client):
    """
    Exhausting one route must not lock the other: a user who mistyped their
    password three times can still create an account.

    sqlite_only for the same reason as the burst test above.
    """
    for _ in range(3):
        _login(client)
    assert _login(client).status_code == 429
    assert _register(client).status_code in (200, 400)


def test_retry_after_header_is_a_positive_integer(client):
    for _ in range(4):
        resp = _login(client)
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0


def test_limit_is_configurable(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 1)
    reset()
    assert _login(client).status_code == 401
    assert _login(client).status_code == 429


def test_window_reset_restores_access(client):
    """Sanity: the limiter is a window, not a permanent ban."""
    for _ in range(4):
        _login(client)
    assert _login(client).status_code == 429
    reset()
    assert _login(client).status_code == 401


def test_rate_limited_response_does_not_leak_whether_the_account_exists(client):
    detail = _login(client, "definitely-not-a-user@example.com").json()["detail"]
    for _ in range(3):
        _login(client, "definitely-not-a-user@example.com")
    limited = _login(client, "definitely-not-a-user@example.com").json()["detail"]
    assert "Too many attempts" in limited
    assert "password" not in limited.lower()
    assert detail != limited
