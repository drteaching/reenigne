"""
Test environment. These vars must be set before `app` is imported: db.py
builds its engine at module scope and get_settings() is lru_cached, so any
later change would not take effect.
"""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="reenigne-test-")

os.environ.update(
    {
        "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP}/test.db",
        # Local JWT auth path (no Supabase) — must be a real key or the app
        # refuses to start, which is itself asserted in test_config.py.
        "API_SECRET_KEY": "test-only-secret-key-not-used-anywhere-real",
        "SUPABASE_URL": "",
        "SUPABASE_JWT_SECRET": "",
        "ENABLE_DEV_ENDPOINTS": "true",
        "STRIPE_SECRET_KEY": "",
        "OPENAI_API_KEY": "test-key",
        "XAI_API_KEY": "test-key",
        "PRO_MINUTES_PER_MONTH": "10",
        "PRO_MAX_FRAMES_PER_SESSION": "5",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def settings():
    return get_settings()


_counter = {"n": 0}


def _register(client):
    _counter["n"] += 1
    email = f"user{_counter['n']}@example.com"
    resp = client.post(
        "/v1/auth/register", json={"email": email, "password": "hunter2hunter2"}
    )
    assert resp.status_code == 200, resp.text
    return email, {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def user(client):
    """Register a fresh user and return (email, auth headers)."""
    return _register(client)


@pytest.fixture
def other_user(client):
    """
    A second, distinct user.

    Not derived from `user`: pytest caches fixtures per test, so requesting
    `user` and `subscribed_user` together yields the same account — which
    would silently make cross-user isolation tests pass for the wrong reason.
    """
    return _register(client)


@pytest.fixture
def subscribed_user(client, user):
    """A user with an active subscription, via the dev activation endpoint."""
    email, headers = user
    resp = client.post("/v1/dev/activate", headers=headers)
    assert resp.status_code == 200, resp.text
    return email, headers
